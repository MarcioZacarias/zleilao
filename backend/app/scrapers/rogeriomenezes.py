"""Rogério Menezes (leiloeiro oficial, Rio de Janeiro/RJ) — HTML renderizado
no servidor pela plataforma Wtis. Vende veiculos de seguradora, banco e
locadora, alem de sucatas, equipamentos e um ou outro imovel judicial.

Listagem: `/categorias/<slug>` (carros, motos, caminhoes, sucatas,
equipamentos, imoveis; `/categorias` = tudo). Traz TODOS os lotes da categoria
numa pagina so', agrupados por data do pregao em
`.filtro-uni__grupo[data-data]` com cards `article.fu-card`. Nao ha'
paginacao: `?page=N` devolve a mesma pagina. Cada entrada de `pages` conta
como uma pagina para `max_pages`.

O card nao traz o id do leilao, so' titulo, data e hora. A agenda `/leiloes`
embute `var AGENDA = [...]` (id, titulo, data, judicial, tipo, status,
comitentes) e e' lida uma vez por coleta para casar card -> leilao; sem ela o
leilao ganha um id sintetico `<data>-<slug-do-titulo>`.

Detalhe (opcional) embute `var lote = {...}` e `var leilao = {...}` (lance
inicial, incremento, visitacao, retirada, comissao, modalidade, judicial) e,
em HTML, especificacoes (marca, ano fab./modelo, categoria), galeria, edital
e estado do lance. Nao ha' cidade/UF por lote: a localizacao vem do endereco
de visitacao, quase sempre o patio do leiloeiro na Av. Brasil, 51.467.

robots.txt: Allow / ; Disallow /api, /uapi, /Lote/Presencial* (nao usados).
Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.rogeriomenezes")

# `tipo` do leilao no JSON da agenda/detalhe (funcao `modalidade()` do JS da agenda)
MODALITY_BY_TIPO = {0: "online", 1: "presencial", 2: "hibrido"}
# `data-tipo` do card quando a agenda nao esta' disponivel
MODALITY_BY_LABEL = {"online": "online", "presencial": "presencial", "online e presencial": "hibrido"}

# Nome que a fonte da' a categoria no detalhe (`.lot-detail__category`) -> dica
# de categoria do projeto. So' usado quando a listagem foi `/categorias` (sem
# categoria na URL).
CATEGORIA_FONTE_MAP = (
    ("sucata", "sucatas"), ("moto", "motos"), ("pesad", "caminhoes"), ("caminh", "caminhoes"),
    ("leve", "carros"), ("imov", "imoveis"), ("ponto comercial", "imoveis"), ("apartamento", "imoveis"),
    ("casa", "imoveis"), ("terreno", "imoveis"), ("equipamento", "equipamentos"), ("material", "equipamentos"),
)

FUEL_RE = re.compile(r"\b(FLEX|GASOLINA|DIESEL|HIBRIDO|ELETRICO|GNV|ALCOOL|ETANOL)\b")
YEARS_RE = re.compile(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b")
KM_RE = re.compile(r"com\s+([\d\.]+)\s*km", re.I)
TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*h?\s*(?:[·•\-–|]\s*(.+?))?\s*$")
# Patio do leiloeiro (rodape do site: "Av. Brasil, 51.467 – Campo Grande, Rio de
# Janeiro/RJ"). O texto de visitacao diz so' "Campo Grande / RJ", que o parser
# generico leria como cidade; Campo Grande e' bairro do Rio.
YARD_RE = re.compile(r"av\.?\s*brasil,?\s*51\.?467", re.I)


class RogerioMenezesScraper(BaseScraper):
    display_name = "Rogério Menezes"
    default_config = {
        "pages": ["/categorias/carros", "/categorias/motos", "/categorias/caminhoes", "/categorias/sucatas"],
        "max_pages": 10,
        "fetch_details": True,
        "max_details_per_run": 60,
    }
    AUCTIONEER_NAME = "Rogério Menezes Nunes"
    AUCTIONEER_REGISTRATION = "JUCERJA 053/89"

    @property
    def default_base_url(self) -> str:
        return "https://rogeriomenezes.com.br"

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        agenda = await self._load_agenda()
        pages = list(self.cfg("pages", self.default_config["pages"]))
        max_pages = int(self.cfg("max_pages", 10))
        for n, path in enumerate(pages, start=1):
            if n > max_pages:
                self.stats.mark_partial(f"parou em {max_pages} paginas com {len(pages) - max_pages} categorias por visitar")
                break
            url = self.abs_url(path)
            try:
                html = await self.fetch(url)
            except Exception as exc:
                # Categoria nao vista: nao da' para concluir que um lote dela sumiu (RN-005).
                self.stats.errors += 1
                self.stats.mark_partial(f"falha ao carregar {path}")
                logger.warning("[RogerioMenezes] falha na pagina %s: %s", url, exc)
                continue
            self.stats.pages += 1
            parsed = self.parse_listing(html, path, agenda)
            logger.info("[RogerioMenezes] %s: %d cards", path, len(parsed))
            items.extend(parsed)
            if n < min(len(pages), max_pages):
                await self.delay()

        if self.fetch_details:
            fetched = 0
            for it in items:
                if fetched >= self.max_details:
                    self.stats.notes.append(f"limite de {self.max_details} detalhes atingido")
                    break
                try:
                    await self.delay()
                    html = await self.fetch(it.official_url)
                    self.enrich_from_detail(it, html)
                    fetched += 1
                    self.stats.details += 1
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[RogerioMenezes] detalhe falhou %s: %s", it.official_url, exc)
        return items

    # ── agenda (mapa card -> leilao) ─────────────────────────────────

    async def _load_agenda(self) -> list[dict]:
        try:
            html = await self.fetch(self.abs_url("/leiloes"))
        except Exception as exc:
            self.stats.errors += 1
            self.stats.notes.append("agenda indisponivel: leiloes identificados por titulo+data")
            logger.warning("[RogerioMenezes] agenda falhou: %s", exc)
            return []
        agenda = self.parse_agenda(html)
        await self.delay()
        return agenda

    @classmethod
    def parse_agenda(cls, html: str) -> list[dict]:
        data = cls._embedded_json(html, "AGENDA")
        return [a for a in data if isinstance(a, dict) and a.get("id")] if isinstance(data, list) else []

    @staticmethod
    def _embedded_json(html: str, var: str) -> Any:
        """`var <nome> = {...};` embutido no HTML. `raw_decode` respeita o
        aninhamento (a agenda tem listas dentro de listas), o que um regex
        nao-guloso nao faria."""
        m = re.search(r"var\s+%s\s*=\s*(?=[\[{])" % re.escape(var), html)
        if not m:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(html, m.end())
        except ValueError:
            return None
        return value

    @staticmethod
    def _norm(text: str | None) -> str:
        return re.sub(r"\s+", " ", unidecode(text or "")).strip().lower()

    @classmethod
    def _match_auction(cls, agenda: list[dict], title: str, date: str, hour: str | None) -> Optional[dict]:
        """Casa pelo titulo + data; a hora desempata quando ha' dois no mesmo dia."""
        t = cls._norm(title)
        if not t or not date:
            return None
        same_day = [a for a in agenda if cls._norm(a.get("titulo")) == t and str(a.get("data", ""))[:10] == date]
        if hour and len(same_day) > 1:
            same_day = [a for a in same_day if str(a.get("data", ""))[11:16] == hour] or same_day
        return same_day[0] if same_day else None

    # ── listagem ─────────────────────────────────────────────────────

    @staticmethod
    def _hint_from_path(path: str) -> Optional[str]:
        seg = path.rstrip("/").split("?")[0].split("/")[-1]
        return seg if seg and seg != "categorias" else None

    @staticmethod
    def _hint_from_categoria_fonte(text: str | None) -> Optional[str]:
        t = unidecode(text or "").lower()
        return next((slug for key, slug in CATEGORIA_FONTE_MAP if key in t), None) if t else None

    @staticmethod
    def _origem(*texts: str | None) -> Optional[str]:
        t = unidecode(" ".join(x for x in texts if x)).lower()
        if "segurad" in t:
            return "seguradora"
        if "financeir" in t or "banco" in t:
            return "financeira"
        if "locadora" in t:
            return "locadora"
        return None

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", unidecode(text or "").lower())).strip("-")

    @staticmethod
    def _title_facts(title: str) -> dict[str, Any]:
        """'FIAT PALIO FIRE 2010/2011 FLEX' -> anos e combustivel."""
        out: dict[str, Any] = {}
        t = unidecode(title or "").upper()
        m = YEARS_RE.search(t)
        if m:
            out["ano_fabricacao"], out["ano_modelo"] = int(m.group(1)), int(m.group(2))
        m = FUEL_RE.search(t)
        if m:
            out["combustivel"] = m.group(1).lower()
        return out

    def parse_listing(self, html: str, path: str = "", agenda: list[dict] | None = None) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        hint = self._hint_from_path(path)
        for card in soup.select("article.fu-card"):
            try:
                item = self._parse_card(card, hint, agenda or [], path)
                if item:
                    out.append(item)
            except Exception as exc:  # um card quebrado nao derruba a pagina
                self.stats.errors += 1
                logger.debug("[RogerioMenezes] card ignorado: %s", exc)
        return out

    def _parse_card(self, card, hint: Optional[str], agenda: list[dict], path: str) -> Optional[ScrapedItem]:
        link = card.select_one("a.fu-card__link[href]") or card.select_one("a[href*='/lote/']")
        href = link.get("href", "") if link else ""
        m = re.search(r"/lote/(\d+)", href)
        if not m:
            return None
        external_id = m.group(1)
        url = self.strip_tracking(self.abs_url(href))

        title_el = card.select_one(".fu-card__titulo")
        img = card.select_one(".fu-card__foto img")
        title = self.clean_text(title_el.get_text()) if title_el else self.clean_text(img.get("alt") if img else "")
        if not title:
            return None
        image_url = self.reject_placeholder(img.get("src")) if img else None

        num_el = card.select_one(".fu-card__numero")
        lot_number = None
        if num_el:
            lot_number = re.sub(r"(?i)^\s*lote\s*", "", self.clean_text(num_el.get_text())).lstrip("0") or None

        label_el = card.select_one(".fu-card__valor span")
        value_el = card.select_one(".fu-card__valor strong")
        value_text = self.clean_text(value_el.get_text()) if value_el else ""
        price = self.parse_brl(value_text) if value_text else None
        price_kind = "lance_atual" if label_el and "atual" in label_el.get_text().lower() else "lance_inicial"
        # "Consultar": lance divulgado so' no pregao. Fica registrado, nao vira valor (RN-002).
        lance_texto = value_text if value_text and price is None else None

        specs_el = card.select_one(".fu-card__specs")
        specs = self.clean_text(specs_el.get_text()) if specs_el else None
        km = None
        if specs:
            mk = KM_RE.search(specs)
            if mk:
                try:
                    km = int(mk.group(1).replace(".", ""))
                except ValueError:
                    km = None

        leilao_el = card.select_one(".fu-card__leilao")
        leilao_title = self.clean_text(leilao_el.get_text()) if leilao_el else ""
        time_el = card.select_one(".fu-card__time span")
        hour, committer = None, None
        if time_el:
            mt = TIME_RE.match(self.clean_text(time_el.get_text()))
            if mt:
                hour = mt.group(1).zfill(5)
                committer = self.clean_text(mt.group(2)) or None
        date = (card.get("data-data") or "").strip()
        starts_at = self.parse_datetime_br(f"{date} {hour}" if hour else date) if date else None

        tipo_label = self.clean_text(card.get("data-tipo") or "")
        judicial = tipo_label.lower() == "judicial" or card.select_one(".fu-card__judicial") is not None
        cat_el = card.select_one(".fu-card__cat")
        categoria_fonte = self.clean_text(cat_el.get_text()) if cat_el else None

        entry = self._match_auction(agenda, leilao_title, date, hour)
        status_hint = None
        if entry:
            auction_ext = str(entry["id"])
            auction_url = self.abs_url(f"/leilao/{entry['id']}")
            judicial = judicial or bool(entry.get("judicial"))
            modality = MODALITY_BY_TIPO.get(entry.get("tipo"))
            status_hint = self.status_from_text(entry.get("statusLabel")) or ("open" if entry.get("aberto") else None)
            # Comitentes do leilao inteiro (bancos, seguradoras, locadoras, tribunal):
            # o do lote fica em raw_attributes porque o modelo guarda um por leilao.
            names = list(dict.fromkeys(n for n in (entry.get("nomes") or []) if n))
            auction_committer = ", ".join(names) if names else committer
        else:
            auction_ext = f"{date}-{self._slug(leilao_title)}" if date and leilao_title else f"lot-{external_id}"
            auction_url = self.abs_url(path)
            modality = MODALITY_BY_LABEL.get(tipo_label.lower())
            auction_committer = committer

        auction = ScrapedAuction(
            external_id=auction_ext,
            title=leilao_title or None,
            auctioneer_name=self.AUCTIONEER_NAME,
            auctioneer_registration=self.AUCTIONEER_REGISTRATION,
            committer_name=auction_committer,
            modality=modality,
            auction_type="judicial" if judicial else "extrajudicial",
            official_url=auction_url,
            # Sem min_bid: a sessao e' do leilao inteiro e o lance de cada lote ja' esta' em `price`.
            sessions=[ScrapedSession(kind="unica", starts_at=starts_at)],
        )

        raw: dict[str, Any] = {
            "comitente": committer,
            "acessorios": specs,
            "km": km,
            "lance_texto": lance_texto,
            "tipo_pregao": tipo_label or None,
            "leilao_titulo": leilao_title or None,
            "categoria_fonte": categoria_fonte,
            "origem": "judicial" if judicial else self._origem(leilao_title),
            **self._title_facts(title),
        }
        return ScrapedItem(
            external_id=external_id,
            title=title,
            official_url=url,
            price=price,
            price_kind=price_kind,
            lot_number=lot_number,
            image_url=image_url,
            images=[image_url] if image_url else [],
            description=specs,
            raw_attributes={k: v for k, v in raw.items() if v is not None},
            category_hint=hint or self._hint_from_categoria_fonte(categoria_fonte),
            status_hint=status_hint,
            auction=auction,
            raw_payload=str(card),
        )

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        lote = self._embedded_json(html, "lote") or {}
        leilao = self._embedded_json(html, "leilao") or {}
        raw = item.raw_attributes

        # Descricao em HTML tem caixa normal; o JSON vem todo em maiusculas.
        desc_el = soup.select_one(".lot-detail__desc")
        desc = self.clean_text(desc_el.get_text(" ")) if desc_el else self.clean_text(lote.get("descricao"))
        obs_el = soup.select_one(".lot-detail__observations")
        obs = re.sub(r"(?i)^\s*observa[cç][oõ]es:\s*", "", self.clean_text(obs_el.get_text(" "))) if obs_el else self.clean_text(lote.get("observacao"))
        parts = [p for p in (desc, f"Observações: {obs}" if obs else None) if p]
        if parts:
            item.description = "\n".join(parts)
        if obs:
            raw["observacoes"] = obs

        fields: dict[str, str] = {}
        for spec in soup.select(".lot-detail__spec"):
            dt, dd = spec.find("dt"), spec.find("dd")
            if dt and dd:
                fields[unidecode(self.clean_text(dt.get_text())).lower()] = self.clean_text(dd.get_text(" "))
        if fields.get("marca"):
            raw["marca"] = fields["marca"]
        years = YEARS_RE.search(fields.get("ano fab./modelo", ""))
        if years:
            raw["ano_fabricacao"], raw["ano_modelo"] = int(years.group(1)), int(years.group(2))
        cat_el = soup.select_one(".lot-detail__category")
        categoria_fonte = fields.get("categoria") or (self.clean_text(cat_el.get_text()) if cat_el else None)
        if categoria_fonte:
            raw["categoria_fonte"] = categoria_fonte
            item.category_hint = item.category_hint or self._hint_from_categoria_fonte(categoria_fonte)
        if not item.lot_number:
            badge = soup.select_one(".lot-detail__lote-badge")
            num = fields.get("lote") or (re.sub(r"(?i)^\s*lote\s*", "", self.clean_text(badge.get_text())) if badge else "")
            item.lot_number = num.lstrip("0") or None

        if lote:
            inicial = self.parse_brl(lote.get("valorInicial"))
            if inicial is not None:
                raw["lance_inicial"] = str(inicial)
                if item.price is None:
                    item.price, item.price_kind = inicial, "lance_inicial"
            incremento = self.parse_brl(lote.get("valorIncremento"))
            if incremento is not None:
                raw["incremento"] = str(incremento)
            if lote.get("condicao") is not None:
                raw["condicao_codigo"] = lote["condicao"]  # 7 = Sucata no filtro do leilao; demais sem legenda publica
        estado = soup.select_one(".lance-box__estado")
        status = self.status_from_text(estado.get_text() if estado else None)
        if status:
            item.status_hint = status

        edital = soup.select_one("a.lot-detail__info-btn--edital[href]")
        if edital:
            raw["edital_url"] = self.abs_url(edital["href"])
        vis_el = soup.select_one(".lote-visitacao")
        visitacao = self.clean_text(vis_el.get_text(" ")) if vis_el else self.clean_text(leilao.get("infoVisitacao"))
        if visitacao:
            raw["visitacao"] = visitacao
        if leilao.get("infoRetirada"):
            raw["retirada"] = self.clean_text(leilao["infoRetirada"])
        comissao = self.parse_brl(leilao.get("valorComissao"))
        if comissao is not None:
            # "5.00" -> "5", "10.00" -> "10" (normalize() daria "1E+1")
            raw["comissao_pct"] = f"{comissao:f}".rstrip("0").rstrip(".") or "0"
        # Endereco do pregao (so' nos hibridos/presenciais) ou de visitacao
        facts = [self.clean_text(f.get_text(" ")) for f in soup.select(".lot-detail__fact") if "fact--status" not in " ".join(f.get("class", []))]
        address = next((f for f in facts if re.search(r"\d", f) and not f.lower().startswith("leil")), None)
        location = address or visitacao
        if location:
            item.location_text = location
            if not item.city or not item.state:
                city, state = self._city_state(location)
                item.city, item.state = item.city or city, item.state or state

        if leilao.get("id"):
            judicial = bool(leilao.get("judicial"))
            if item.auction is None:
                item.auction = ScrapedAuction(external_id=str(leilao["id"]))
            a = item.auction
            a.external_id = str(leilao["id"])
            a.title = self.clean_text(leilao.get("titulo")) or a.title
            a.official_url = self.abs_url(f"/leilao/{leilao['id']}")
            a.auction_type = "judicial" if judicial else "extrajudicial"
            a.modality = MODALITY_BY_TIPO.get(leilao.get("tipo"), a.modality)
            a.auctioneer_name = a.auctioneer_name or self.AUCTIONEER_NAME
            a.auctioneer_registration = a.auctioneer_registration or self.AUCTIONEER_REGISTRATION
            opened = self.parse_datetime_br(((leilao.get("dataAbertura") or {}).get("date")) or "")
            if opened:
                if a.sessions:
                    a.sessions[0].starts_at = opened
                else:
                    a.sessions.append(ScrapedSession(kind="unica", starts_at=opened))
            if leilao.get("instancia"):
                raw["instancia"] = leilao["instancia"]
            raw["origem"] = "judicial" if judicial else (self._origem(leilao.get("descricao"), leilao.get("titulo")) or raw.get("origem"))
            if raw.get("origem") is None:
                raw.pop("origem", None)

        imgs: list[str] = []
        for a_el in soup.select("ul.lote-thumbs li a[href]"):
            u = a_el["href"]
            if u.startswith("http") and u not in imgs:
                imgs.append(u)
        main_img = soup.select_one("#lote-image[src]")
        if not imgs and main_img:
            imgs.append(main_img["src"])
        if imgs:
            item.images = imgs[:12]
        foto = (lote.get("fotoDestaque") or {})
        item.image_url = item.image_url or foto.get("min") or foto.get("thumb") or (imgs[0] if imgs else None)
        item.raw_payload = (item.raw_payload or "") + "\n<!-- detail -->\n" + json.dumps(
            {"lote": lote, "leilao": leilao, "specs": fields}, ensure_ascii=False)

    @classmethod
    def _city_state(cls, text: str) -> tuple[Optional[str], Optional[str]]:
        if YARD_RE.search(unidecode(text)):
            return "Rio de Janeiro", "RJ"
        city, state = cls.parse_city_state(text)
        # Sem UF reconhecida o "cidade" seria o endereco inteiro em title case.
        return (city, state) if state else (None, None)
