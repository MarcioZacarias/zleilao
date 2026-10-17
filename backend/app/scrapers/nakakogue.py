"""Nakakogue Leilões (Curitiba/PR) — PHP renderizado no servidor, sem API.

Estrutura do site:
- Capa `/`: `ul.leiloes > li` sao os LEILOES (pregoes), com titulo ("1º Leilão -
  Vara X", "Hasta Única - ...", "Venda Direta - ..."), data, local e edital.
  A capa nao lista todos os pregoes: lotes de leiloes ausentes dela ainda
  aparecem na consulta por categoria, por isso o indice e' opcional.
- `/lotes/consulta/{N}/`: lotes por categoria (1 Imoveis, 2 Veiculos, 3 Maquinas,
  4 Venda Direta, 5 todos). Vem tudo numa pagina; a paginacao e' client-side
  (jPages), entao nao ha' `?pagina=`. Card em `ul.lotes#itemContainer > li`,
  sem foto.
- Detalhe `/detalhe-lote/{leilao}/{lote}/`: casca HTML preenchida por JS. Abrir a
  casca grava o lote na sessao PHP; `POST /proximo_lote.php` sem parametros
  devolve o JSON do lote (descricao, fotos, obs com 1º/2º leilao e lances
  minimos, autos, onus). Sao duas requisicoes por lote, no mesmo cookie jar.

Charset: o servidor declara iso-8859-1, mas parte dos registros chega em UTF-8
gravado como latin-1 ("1Âº LeilÃ£o"). O reparo e' feito campo a campo.

robots.txt libera tudo (Allow: /). Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from bs4 import BeautifulSoup
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.nakakogue")

# Nome da categoria na fonte -> dica que o classificador entende (HINT_MAP).
# "Sucata autorizados Detran" e' veiculo baixado: entra como sucata, e o
# titulo decide a folha. COPEL/Diversos ficam sem dica (classificador cai em
# "diversos" ou na palavra-chave do titulo).
CATEGORY_HINTS = {
    "veiculos": "veiculos",
    "sucata autorizados detran": "sucatas",
    "maquinas e equipamentos": "maquinas",
    "imoveis": "imoveis",
}

# Marcadores de pregao judicial no titulo do leilao ou no nome do comitente.
JUDICIAL_MARKERS = (
    "vara", "juizado", "hastas", "forum", "comarca", "tribunal", "justica",
    "massa falida", "falencia", "recuperacao judicial",
)

# Frase de rodape que a fonte repete em todo lote; nao e' descricao do bem.
BOILERPLATE_RE = re.compile(
    r"Confira o edital,.*?Detalhes Especiais\s*\(abaixo das fotos\)\.?", re.I | re.S)

PRACA_DATE_RE = re.compile(
    r"Data do (\d)\s*[ºo°ª]?\s*Leil[ãa]o:?\s*(\d{2}/\d{2}/\d{4})(?:\s*[àa]s\s*(\d{1,2}[:h]\d{2}))?", re.I)
PRACA_BID_RE = re.compile(
    r"Lance M[ií]nimo\s*(?:do\s*)?(\d)\s*[ºo°ª]?\s*Leil[ãa]o:?\s*R?\$?\s*([\d\.]+(?:,\d{1,2})?)", re.I)


class NakakogueScraper(BaseScraper):
    display_name = "Nakakogue Leilões"
    default_config = {
        "categorias": [2, 3],  # 2 = Veiculos, 3 = Maquinas (lotes/consulta/N)
        "index_home": True,  # le a capa para titulo/data/local dos pregoes
        "fetch_details": True,
        "max_details_per_run": 60,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.nakakogueleiloes.com.br"

    async def scrape(self) -> list[ScrapedItem]:
        auctions: dict[str, dict[str, Any]] = {}
        if str(self.cfg("index_home", True)).lower() in ("1", "true", "yes"):
            try:
                auctions = self.parse_home(await self.fetch(self.base_url + "/"))
                self.stats.pages += 1
                logger.info("[Nakakogue] capa: %d pregoes", len(auctions))
            except Exception as exc:
                # Sem a capa os lotes saem com titulo generico e sem data;
                # nao e' motivo para abortar a coleta.
                self.stats.errors += 1
                self.stats.notes.append("capa indisponivel: pregoes sem titulo/data")
                logger.warning("[Nakakogue] falha na capa: %s", exc)
            await self.delay()

        items: list[ScrapedItem] = []
        for cat in self.cfg("categorias", [2, 3]):
            url = f"{self.base_url}/lotes/consulta/{cat}/"
            try:
                html = await self.fetch(url)
            except Exception as exc:
                self.stats.errors += 1
                # Categoria nao vista por inteiro: nao da' para concluir que um
                # lote dela sumiu (RN-005).
                self.stats.mark_partial(f"categoria {cat} nao carregou")
                logger.warning("[Nakakogue] falha na categoria %s: %s", cat, exc)
                continue
            self.stats.pages += 1
            parsed = self.parse_listing(html, auctions)
            logger.info("[Nakakogue] categoria %s: %d lotes", cat, len(parsed))
            items.extend(parsed)
            await self.delay()

        if self.fetch_details:
            fetched = 0
            for it in items:
                if fetched >= self.max_details:
                    self.stats.notes.append(f"limite de {self.max_details} detalhes atingido")
                    break
                try:
                    await self.delay()
                    shell = await self.fetch(it.official_url)
                    payload = await self._fetch_lot_payload(it)
                    self.enrich_from_detail(it, shell, payload)
                    fetched += 1
                    self.stats.details += 1
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Nakakogue] detalhe falhou %s: %s", it.official_url, exc)
        return items

    async def _fetch_lot_payload(self, item: ScrapedItem) -> dict[str, Any]:
        """JSON do lote que a casca HTML carrega via `proximo_lote.php`.

        O endpoint nao recebe o lote: responde o que a sessao PHP guardou ao
        abrir a casca. Por isso o GET da casca vem imediatamente antes, no
        mesmo client (cookie jar), e a resposta e' conferida contra o lote.
        """
        assert self.client is not None, "use 'async with scraper:'"
        resp = await self.client.post(
            f"{self.base_url}/proximo_lote.php",
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": item.official_url,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or str(payload.get("ret")) != "1":
            raise ValueError("proximo_lote.php sem lote na sessao")
        got = str(payload.get("lote") or "").lstrip("0")
        if got and got != (item.lot_number or "").lstrip("0"):
            raise ValueError(f"sessao devolveu o lote {got}, esperado {item.lot_number}")
        return payload

    # ── helpers de texto ─────────────────────────────────────────────

    @staticmethod
    def fix_mojibake(text: str | None) -> str:
        """Repara UTF-8 que a fonte serviu como latin-1 ("Ã£" -> "ã").

        Um texto latin-1 legitimo quase nunca forma uma sequencia UTF-8 valida
        (o "ª" de "2ª Vara" e' um byte de continuacao solto), entao o round
        trip falha e o texto original e' mantido.
        """
        if not text:
            return ""
        if not any("\x80" <= ch <= "\xff" for ch in text):
            return text
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text

    @classmethod
    def norm(cls, text: str | None) -> str:
        # Ordinais antes do unidecode: "2°Leilão" viraria "2degleilao".
        t = cls.fix_mojibake(text).replace("°", "o").replace("º", "o").replace("ª", "a")
        return unidecode(t).lower().strip()

    @classmethod
    def auction_type_from_text(cls, text: str | None) -> Optional[str]:
        t = cls.norm(text)
        if not t:
            return None
        if "extrajudicial" in t:
            return "extrajudicial"
        if re.search(r"\bjudicial\b", t) or any(k in t for k in JUDICIAL_MARKERS):
            return "judicial"
        return None

    @classmethod
    def session_kind_from_title(cls, title: str | None) -> str:
        """"1º Leilão" -> 1a_praca; "2º/3º Leilão" -> 2a_praca; "Hasta Única" ->
        unica; "Venda Direta" -> repasse (venda apos pregao, aceita proposta)."""
        t = cls.norm(title)
        if "venda direta" in t:
            return "repasse"
        if "hasta unica" in t or "leilao unico" in t:
            return "unica"
        m = re.search(r"(\d)\s*[ºo°ªa]?\s*leil", t)
        if m:
            # Nao ha' kind para 3º leilao; e' uma nova rodada com preco
            # reduzido, o que o modelo representa como 2a praca.
            return "1a_praca" if m.group(1) == "1" else "2a_praca"
        return "unica"

    @staticmethod
    def status_from_situacao(text: str | None) -> Optional[str]:
        t = unidecode(text or "").lower()
        if "venda" in t or "aberto" in t:
            return "open"
        if "vendido" in t or "arrematado" in t:
            return "sold"
        if "suspenso" in t or "retirado" in t or "cancelado" in t:
            return "withdrawn"
        return BaseScraper.status_from_text(t)

    # ── capa (indice de pregoes) ─────────────────────────────────────

    def parse_home(self, html: str) -> dict[str, dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, dict[str, Any]] = {}
        for li in soup.select("ul.leiloes > li"):
            link = li.select_one("a.link-lote[href]")
            m = re.search(r"lotes/(\d+)", link.get("href", "")) if link else None
            if not m:
                continue
            title_el = li.select_one("h2.titulo-leilao")
            title = self.clean_text(self.fix_mojibake(
                title_el.get_text() if title_el else (link.get("title") or "")))
            date_el = li.select_one("h3.data-leilao")
            starts_at = self.parse_datetime_br(date_el.get_text(" ")) if date_el else None
            local = visita = None
            for h4 in li.select("h4.local"):
                txt = self.clean_text(self.fix_mojibake(h4.get_text(" "))).replace("Ver Mapa", "").strip(" -")
                if txt.lower().startswith("local:"):
                    local = txt.split(":", 1)[1].strip(" -") or None
                elif "visita" in unidecode(txt.lower()):
                    visita = txt.split(":", 1)[1].strip(" -") or None
            edital = li.select_one("a.btn-edital[href]")
            edital_url = self.abs_url(edital["href"].strip()) if edital and edital.get("href", "").strip() else None
            # Pregao na sede/hotel aceita lance pelo site tambem: hibrido.
            modality = "online" if (local and "www." in local.lower()) else ("hibrido" if local else None)
            out[m.group(1)] = {
                "title": title, "starts_at": starts_at, "local": local, "visitacao": visita,
                "edital_url": edital_url, "modality": modality,
            }
        return out

    # ── listagem por categoria ───────────────────────────────────────

    def parse_listing(self, html: str, auctions: dict[str, dict[str, Any]] | None = None) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        for li in soup.select("ul.lotes > li"):
            try:
                item = self._parse_card(li, auctions or {})
                if item:
                    out.append(item)
            except Exception as exc:  # um card quebrado nao derruba a pagina
                self.stats.errors += 1
                logger.debug("[Nakakogue] card ignorado: %s", exc)
        return out

    def _parse_card(self, li, auctions: dict[str, dict[str, Any]]) -> Optional[ScrapedItem]:
        link = li.select_one("a[href*='detalhe-lote/']")
        m = re.search(r"detalhe-lote/(\d+)/(\w+)", link.get("href", "")) if link else None
        if not m:
            return None
        auction_id, lot_seg = m.group(1), m.group(2)
        lot_number = lot_seg.lstrip("0") or lot_seg
        url = f"{self.base_url}/detalhe-lote/{auction_id}/{lot_seg}/"

        title_el = li.select_one("h3.titulo-lote")
        if not title_el:
            return None
        title = self.clean_text(self.fix_mojibake(title_el.get_text(" ")))
        title = re.sub(r"^\s*0*" + re.escape(lot_number) + r"\s*-\s*", "", title)
        if not title:
            # Alguns titulos vem em <p> dentro do <h3>; o lxml fecha o h3 antes
            # do p, e o texto fica no irmao seguinte.
            sib = title_el.find_next_sibling("p")
            title = self.clean_text(self.fix_mojibake(sib.get_text(" "))) if sib else ""
        title = title or f"Lote {lot_number}"

        fields: dict[str, str] = {}
        edital_url = None
        for span in li.select("section.meio span"):
            small = span.select_one("small")
            if not small:
                continue
            label = unidecode(self.clean_text(small.get_text())).rstrip(":").lower()
            value = self.clean_text(self.fix_mojibake(span.get_text(" ").replace(small.get_text(), "", 1)))
            fields[label] = value
            if label == "edital" and span.a and span.a.get("href"):
                edital_url = self.abs_url(span.a["href"].strip())

        avaliado = self.parse_brl(fields.get("valor avaliado"))
        minimo = self.parse_brl(fields.get("valor minimo"))
        lance_el = li.select_one("h3.titulo-vlr-lance")
        lance_atual = self.parse_brl(lance_el.get_text()) if lance_el else None

        category_text = fields.get("categoria") or None
        category_hint = CATEGORY_HINTS.get(unidecode(category_text or "").lower().strip())
        status_hint = self.status_from_situacao(fields.get("situacao"))

        info = auctions.get(auction_id, {})
        auction_title = info.get("title") or None
        committer = self._best_committer(fields.get("edital"), auction_title)
        auction_type = (self.auction_type_from_text(auction_title)
                        or self.auction_type_from_text(committer))
        kind = self.session_kind_from_title(auction_title) if auction_title else "unica"

        # A fonte mostra como "Valor Mínimo" o piso da 2ª praça mesmo enquanto
        # o lote esta' na 1ª, cujo lance nao pode ficar abaixo da avaliacao
        # (CPC, art. 891). Sem o detalhe, o 1º leilao judicial sai avaliado /
        # minimo; o detalhe confirma com os lances minimos explicitos.
        price, price_second = minimo, None
        if kind == "1a_praca" and auction_type == "judicial" and avaliado and minimo and avaliado > minimo:
            price, price_second = avaliado, minimo
        price_kind = "lance_inicial"
        if lance_atual and lance_atual > 0:
            price, price_kind = lance_atual, "lance_atual"

        sessions = [ScrapedSession(kind=kind, starts_at=info.get("starts_at"), min_bid=price if price_kind == "lance_inicial" else minimo)]
        auction = ScrapedAuction(
            external_id=auction_id,
            title=(auction_title or f"Leilão {auction_id}")[:300],
            auctioneer_name=self.display_name,
            committer_name=committer,
            modality=info.get("modality"),
            auction_type=auction_type,
            official_url=f"{self.base_url}/lotes/{auction_id}/",
            sessions=sessions,
        )

        raw: dict[str, Any] = {
            "categoria_fonte": category_text,
            "valor_avaliacao": str(avaliado) if avaliado is not None else None,
            "valor_minimo": str(minimo) if minimo is not None else None,
            "lance_atual": str(lance_atual) if lance_atual else None,
            "situacao_fonte": fields.get("situacao") or None,
            "edital_url": edital_url or info.get("edital_url"),
            "local_pregao": info.get("local"),
            "visitacao": info.get("visitacao"),
        }
        if kind == "repasse":
            raw["venda_direta"] = True
        if category_hint in ("veiculos", "sucatas"):
            raw.update(self._vehicle_from_title(title))

        city, state = self._city_state_from_title(auction_title)
        return ScrapedItem(
            external_id=f"{auction_id}-{lot_seg}",
            title=title,
            official_url=url,
            price=price,
            price_kind=price_kind,
            price_second=price_second,
            lot_number=lot_number,
            city=city,
            state=state,
            raw_attributes={k: v for k, v in raw.items() if v is not None},
            category_hint=category_hint,
            status_hint=status_hint,
            auction=auction,
            raw_payload=str(li),
        )

    @classmethod
    def _best_committer(cls, edital_text: str | None, auction_title: str | None) -> Optional[str]:
        """O rotulo do edital no card e' cortado em ~23 caracteres ("DIVISAO DE
        HASTAS PUBLI"); o titulo do pregao costuma trazer o nome inteiro."""
        edital_text = re.sub(r"^0+(?=\d)", "", cls.clean_text(edital_text))
        if not edital_text:
            return None
        head = unidecode(edital_text).lower()[:15]
        for seg in (auction_title or "").split(" - "):
            seg = seg.strip()
            if len(seg) > len(edital_text) and unidecode(seg).lower().startswith(head):
                return seg[:200]
        return edital_text[:200]

    @staticmethod
    def _city_state_from_title(auction_title: str | None) -> tuple[Optional[str], Optional[str]]:
        """"... - Casa bairro Uberaba, Curitiba/PR" -> (Curitiba, PR). So' quando o
        titulo termina em cidade/UF; o detalhe traz o municipio do proprio bem."""
        m = re.search(r"([A-Za-zÀ-ÿ'\. ]{3,}?)\s*/\s*([A-Z]{2})\s*$", auction_title or "")
        if not m:
            return None, None
        return m.group(1).strip().title(), m.group(2)

    @staticmethod
    def _vehicle_from_title(title: str) -> dict[str, Any]:
        """"HYUNDAI/TUCSON GLSB, 2012/2013" -> marca, modelo, anos. E' dica para a
        extracao; placa/chassi/RENAVAM ficam so' no texto, que o normalizador
        mascara."""
        out: dict[str, Any] = {}
        m = re.search(r"\b([A-Z][A-Z0-9\.\-]{1,15})/([A-Z0-9][A-Z0-9 \.\-]{1,40}?)(?=\s*[,;]|\s+[\-–]\s|\s+\d{4}/|\s*$)", title)
        if m and not re.fullmatch(r"[A-Z]{2}", m.group(2).strip()):
            out["marca"] = m.group(1).strip().title()
            out["modelo"] = m.group(2).strip().title()
        m = re.search(r"Ano(?:\s*de\s*Fabrica[cç][aã]o)?\s*/?\s*(?:Modelo)?:?\s*(\d{4})\s*/\s*(\d{2,4})", title, re.I)
        if not m:
            m = re.search(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b", title)
        if m:
            out["ano_fabricacao"] = int(m.group(1))
            if len(m.group(2)) == 4:  # "1999/19" e' corte do titulo: ano/modelo fica sem
                out["ano_modelo"] = int(m.group(2))
        return out

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, shell_html: str, payload: dict[str, Any]) -> None:
        shell = BeautifulSoup(shell_html, "lxml")
        nav = shell.select_one("span.data-leilao-nav")
        nav_date = self.parse_datetime_br(self.fix_mojibake(nav.get_text())) if nav else None
        edital = shell.select_one("div#edital")
        if edital and self.clean_text(edital.get_text()):
            item.raw_attributes["edital_url"] = self.clean_text(edital.get_text())

        obs_html = " ".join(str(x) for x in (payload.get("obs") or []))
        text = self.clean_text(BeautifulSoup(obs_html, "lxml").get_text(" "))
        text = BOILERPLATE_RE.sub("", text)
        text = re.sub(r"\s*_(?=\s|$)", " ", text)  # separador interno da fonte
        text = re.sub(r"R\$\s*-\s*", "R$ ", text)
        produtos = re.findall(r"N[ºo°]\.?\s*Produto:\s*(\d+)", text)
        if len(produtos) <= 1:
            text = re.sub(r"N[ºo°]\.?\s*Produto:\s*\d+\s*", "", text)
        else:
            text = re.sub(r"N[ºo°]\.?\s*Produto:\s*(\d+)\s*", r"[Produto \1] ", text)
        text = self.clean_text(text)
        if text:
            item.description = text
        descricao = self.clean_text(str(payload.get("descricao") or ""))
        descricao = re.sub(r"^LOTE\s+\w+\s*", "", descricao, flags=re.I)
        if descricao and (item.title.startswith("Lote ") or len(descricao) > len(item.title)):
            item.title = descricao[:300]

        m = re.search(r"Munic[ií]pio:?\s*([A-Za-zÀ-ÿ'\. ]+?)\s*/\s*([A-Za-z]{2})\b", text)
        if m:
            city = self.reject_unknown(m.group(1).strip().title())
            item.city, item.state = city or item.city, m.group(2).upper()
            item.location_text = f"{m.group(1).strip().title()}/{m.group(2).upper()}"
        for key, pat in (
            # Para na virgula tambem: "Especie: Carga, Tipo: ..., Placa X" nao
            # pode arrastar a placa para os atributos (RN-009).
            ("combustivel", r"Combust[ií]vel:?\s*([^;.,]+)"),
            ("cor", r"\bCor:?\s*([^;.,]+)"),
            ("especie_tipo", r"Esp[ée]cie(?:\s*/\s*Tipo)?:?\s*([^;.,]+)"),
        ):
            mm = re.search(pat, text)
            if mm:
                item.raw_attributes[key] = self.clean_text(mm.group(1))[:60]
        if item.category_hint in ("veiculos", "sucatas"):
            for k, v in self._vehicle_from_title(text[:300]).items():
                item.raw_attributes.setdefault(k, v)

        autos = self.clean_text(str(payload.get("autos") or ""))
        if autos:
            item.raw_attributes["processo"] = autos
        onus = self.parse_brl(str(payload.get("onus") or ""))
        if onus is not None:
            item.raw_attributes["onus"] = str(onus)
        if payload.get("idlote"):
            item.raw_attributes["id_interno"] = str(payload["idlote"])
        if payload.get("sucata"):
            item.raw_attributes["codigo_categoria"] = str(payload["sucata"])
        avaliado = self.parse_brl(str(payload.get("avaliado") or ""))
        if avaliado is not None:
            item.raw_attributes["valor_avaliacao"] = str(avaliado)
        if re.search(r"exclusivamente eletr", unidecode(text).lower()):
            modality = "online"
        else:
            modality = None

        imgs: list[str] = []
        for entry in payload.get("imagem") or []:
            mm = re.search(r"src=['\"]([^'\"]+)['\"]", str(entry))
            if mm:
                u = self.abs_url(mm.group(1).strip())
                if u not in imgs:
                    imgs.append(u)
        if imgs:
            item.images = imgs[:12]
            item.image_url = imgs[0]

        if item.auction:
            # Partes do processo ("partes/") sao dados pessoais: nao buscar (RN-009).
            if autos:
                item.auction.auction_type = "judicial"
            elif item.auction.auction_type is None:
                item.auction.auction_type = "extrajudicial"
            if modality:
                item.auction.modality = modality
            dates = {n: self.parse_datetime_br(f"{d} {h or ''}") for n, d, h in PRACA_DATE_RE.findall(text)}
            bids = {n: self.parse_brl(v) for n, v in PRACA_BID_RE.findall(text)}
            if dates or bids:
                sessions: list[ScrapedSession] = []
                for n in sorted(set(dates) | set(bids)):
                    kind = "1a_praca" if n == "1" else "2a_praca"
                    sessions.append(ScrapedSession(kind=kind, starts_at=dates.get(n), min_bid=bids.get(n)))
                item.auction.sessions = sessions
                if item.price_kind == "lance_inicial":
                    if bids.get("1") is not None:
                        item.price = bids["1"]
                    item.price_second = bids.get("2")
                elif bids.get("2") is not None:
                    item.price_second = bids["2"]
            elif nav_date:
                for s in item.auction.sessions:
                    s.starts_at = s.starts_at or nav_date
            if nav_date and not any(s.starts_at for s in item.auction.sessions):
                item.auction.sessions.append(ScrapedSession(kind="unica", starts_at=nav_date))

        bem_inicial = self.parse_brl(str(payload.get("bem_lance_inicial") or ""))
        if bem_inicial is not None:
            item.raw_attributes["lance_inicial_fonte"] = str(bem_inicial)
            if item.price is None:
                item.price = bem_inicial

        item.raw_payload = (item.raw_payload or "") + "\n<!-- detail -->\n" + json.dumps(payload, ensure_ascii=False)[:50_000]
