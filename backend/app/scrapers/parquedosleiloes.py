"""Parque dos Leilões (Brasília/DF) — Laravel com HTML renderizado no servidor.

Dois niveis. A listagem de pregoes (`/leiloes?searchMode=normal` para os
extrajudiciais e `/leiloes-judiciais?searchMode=judicial` para os judiciais;
`type_id=1` filtra veiculos) traz 12 cards `.auction-card` por pagina, em
ordem decrescente de data: os pregoes abertos vem antes dos encerrados. A
pagina do pregao (`/leilao/{id}/detalhes?page=N`) traz 28 cards
`.auction-lot-card` por pagina.

O card do lote NAO traz preco nem cidade. O lance inicial so' aparece no
detalhe (`/leilao/{id}/lote/{lote}`), que embute um JSON
`data-json="auctionLot"` (datas, status, lance minimo) e uma tabela com
marca/modelo/ano/km/cor/combustivel/sinistro. Por isso, com `fetch_details`
ligado, so' entram os lotes cujo detalhe foi lido: emitir um lote sem preco
faria `jobs.py` apagar o preco gravado no ciclo anterior.

Pracas: cada praca e' um pregao proprio ("... - 1ª PRAÇA"). Nos judiciais, as
observacoes do pregao trazem avaliacao e data das duas pracas.

robots.txt libera tudo (`Disallow:` vazio). Verificado em 17/10/2026.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from bs4 import BeautifulSoup

from app.scrapers.base import MONTHS_PT, BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.parquedosleiloes")

# `lot_status_id` do filtro de busca do site (17/10/2026). "Cancelado" nao
# tem id proprio: vem como texto/classe `canceled` sobre qualquer id.
LOT_STATUS_MAP = {
    "1": "soon",    # O leilao comecara em breve
    "2": "open",    # Leilao aberto para lances
    "3": "open",    # Dou-lhe uma
    "4": "open",    # Dou-lhe duas
    "5": "open",    # Registrando lances presenciais
    "6": "open",    # Dou-lhe tres
    "7": "closed",  # Lote encerrado
    "8": "open",    # Arrematacao condicional: ainda em disputa
}

# A categoria do pregao e' texto livre do leiloeiro ("VEICULOS", "IMÓVEIS",
# "BENS E EQUIPAMENTOS", "CASA GUARA/DF"...). A pasta da foto e' mais
# confiavel: o sistema deles separa veiculos de imoveis no storage.
STORAGE_CATEGORY = {"vehicles": "veiculos", "properties": "imoveis"}

# Orgaos que identificam pregao judicial pelo nome, quando ele nao veio da
# listagem judicial.
COURT_RE = re.compile(r"\b(VARA|JUIZADO|TRIBUNAL|JU[IÍ]ZO|COMARCA|TJDFT|TRT|TRF|JUSTI[CÇ]A)\b", re.I)

PRACA_RE = re.compile(r"([12])\s*[ªa°º]?\s*PRA[ÇC]A", re.I)

# "AVALIAÇÃO : R$ 5.000,00 - 1ª PRAÇA 09/11/2026 ÀS 14H00". O valor as vezes
# vem com espaco espurio ("R$ 2 .500,00"), por isso o grupo aceita espacos.
PRACA_OBS_RE = re.compile(
    r"R\$\s*([\d\s\.]+,\d{2})\s*[-–]\s*([12])\s*[ªa°º]?\s*PRA[ÇC]A\s*[-–:]?\s*"
    r"(\d{2}/\d{2}/\d{4})(?:\s*(?:[ÀA]S?)?\s*(\d{1,2})\s*[Hh:]\s*(\d{2}))?",
    re.I,
)


def parse_date_pt(text: str | None) -> Optional[datetime]:
    """'3 set 2026, 13:00' | '3 de set de 2026 às 13:00' | '28/10/26 14:00:00'."""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip().lower()
    m = re.search(r"(\d{1,2})\s*(?:de\s*)?([a-zç]{3})[a-zç]*\.?\s*(?:de\s*)?(\d{4})(?:\D+(\d{1,2})[:h](\d{2}))?", t)
    if m and m.group(2) in MONTHS_PT:
        try:
            return datetime(int(m.group(3)), MONTHS_PT[m.group(2)], int(m.group(1)),
                            int(m.group(4) or 0), int(m.group(5) or 0))
        except ValueError:
            return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})(?:\D+(\d{1,2}):(\d{2}))?", t)
    if m:
        try:
            return datetime(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)),
                            int(m.group(4) or 0), int(m.group(5) or 0))
        except ValueError:
            return None
    return BaseScraper.parse_datetime_br(text)


@dataclass
class AuctionRef:
    """Card da listagem de pregoes: o suficiente para decidir se vale abrir."""
    external_id: str
    url: str
    title: str
    status_hint: Optional[str] = None
    starts_at: Optional[datetime] = None
    category: Optional[str] = None
    judicial: bool = False


@dataclass
class AuctionContext:
    """Cabecalho do pregao, compartilhado por todos os lotes dele."""
    auction: ScrapedAuction
    category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    location_text: Optional[str] = None
    price_second: Optional[Decimal] = None
    praca_kind: str = "unica"
    extra: dict[str, Any] = field(default_factory=dict)

    def auction_copy(self) -> ScrapedAuction:
        # Cada lote recebe a sua copia: o enriquecimento pelo detalhe mexe nas
        # sessoes e nao pode vazar para os outros lotes do mesmo pregao.
        return replace(self.auction, sessions=[replace(s) for s in self.auction.sessions])


class ParqueDosLeiloesScraper(BaseScraper):
    display_name = "Parque dos Leilões"
    default_config = {
        "auction_lists": [
            "/leiloes?searchMode=normal&type_id=1",
            "/leiloes-judiciais?searchMode=judicial&type_id=1",
        ],
        "include_closed": False,
        "max_list_pages": 5,
        "max_auctions": 10,
        "max_pages": 10,  # paginas de lotes por pregao (28 lotes cada)
        "fetch_details": True,
        "max_details_per_run": 150,
        # O leiloeiro, o patio de exposicao e as varas sao de Brasilia/DF; o
        # lote de veiculo nao diz a cidade. Vale so' quando a pagina nao
        # informa nada; limpe se nao quiser o padrao.
        "default_city": "Brasília",
        "default_state": "DF",
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.parquedosleiloes.com.br"

    def _flag(self, key: str, default: bool) -> bool:
        return str(self.cfg(key, default)).lower() in ("1", "true", "yes")

    # ── ciclo ────────────────────────────────────────────────────────

    async def scrape(self) -> list[ScrapedItem]:
        refs = await self.collect_auctions()
        items: list[ScrapedItem] = []
        max_auctions = int(self.cfg("max_auctions", 10))
        for n, ref in enumerate(refs):
            if n >= max_auctions:
                self.stats.mark_partial(f"limite de {max_auctions} pregoes por ciclo atingido")
                break
            try:
                got = await self.scrape_auction(ref)
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"pregao {ref.external_id} falhou")
                logger.warning("[Parque] pregao %s falhou: %s", ref.url, exc)
                continue
            logger.info("[Parque] pregao %s (%s): %d lotes", ref.external_id, ref.title[:40], len(got))
            items.extend(got)
            await self.delay()

        if not self.fetch_details:
            return items

        # O preco so' existe no detalhe: lote sem detalhe fica fora do ciclo
        # (ver docstring do modulo). O limite e' por ciclo, nao por pregao.
        enriched: list[ScrapedItem] = []
        for it in items:
            if len(enriched) >= self.max_details:
                self.stats.mark_partial(
                    f"limite de {self.max_details} detalhes atingido; lotes restantes ficam para o proximo ciclo")
                break
            try:
                await self.delay()
                html = await self.fetch(it.official_url)
                self.enrich_from_detail(it, html)
                self.stats.details += 1
                enriched.append(it)
            except Exception as exc:
                self.stats.errors += 1
                self.stats.mark_partial(f"detalhe do lote {it.external_id} falhou")
                logger.warning("[Parque] detalhe falhou %s: %s", it.official_url, exc)
        return enriched

    # ── listagem de pregoes ──────────────────────────────────────────

    async def collect_auctions(self) -> list[AuctionRef]:
        include_closed = self._flag("include_closed", False)
        max_list_pages = int(self.cfg("max_list_pages", 5))
        max_auctions = int(self.cfg("max_auctions", 10))
        out: list[AuctionRef] = []
        seen: set[str] = set()
        for path in self.cfg("auction_lists") or self.default_config["auction_lists"]:
            judicial = "judicial" in path.lower()
            for page in range(1, max_list_pages + 1):
                url = self.abs_url(path)
                if page > 1:
                    url = f"{url}{'&' if '?' in url else '?'}page={page}"
                try:
                    html = await self.fetch(url)
                except Exception as exc:
                    self.stats.errors += 1
                    self.stats.mark_partial(f"listagem {path} pagina {page} falhou")
                    logger.warning("[Parque] falha na listagem %s: %s", url, exc)
                    break
                self.stats.pages += 1
                refs = self.parse_auction_list(html, judicial=judicial)
                saw_closed = False
                for ref in refs:
                    if ref.status_hint in ("closed", "withdrawn"):
                        saw_closed = True
                        if not include_closed:
                            continue
                    if ref.external_id in seen:
                        continue
                    seen.add(ref.external_id)
                    out.append(ref)
                if len(out) >= max_auctions:
                    break
                # A listagem e' ordenada por data decrescente: depois do
                # primeiro encerrado so' vem pregao mais antigo. Parar aqui
                # nao torna a varredura parcial, porque todos os abertos ja'
                # foram vistos.
                if not refs or not self._has_next(html) or (saw_closed and not include_closed):
                    break
                if page == max_list_pages:
                    self.stats.mark_partial(f"parou em {max_list_pages} paginas de {path} com mais paginas disponiveis")
                    break
                await self.delay()
            if len(out) >= max_auctions:
                break
        return out

    @staticmethod
    def _has_next(html: str) -> bool:
        return 'rel="next"' in html

    def parse_auction_list(self, html: str, judicial: bool = False) -> list[AuctionRef]:
        soup = BeautifulSoup(html, "lxml")
        out: list[AuctionRef] = []
        for card in soup.select(".auction-card"):
            link = card.select_one("a[href*='/leilao/']")
            m = re.search(r"/leilao/(\d+)/", link.get("href", "")) if link else None
            if not m:
                continue
            name_el = card.select_one(".card-body .name")
            title = self.clean_text(name_el.get_text()) if name_el else f"Leilão {m.group(1)}"
            status_el = card.select_one(".card-body .text .badge")
            date_el = card.select_one(".card-body .date")
            cat_el = card.select_one(".card-body .category")
            out.append(AuctionRef(
                external_id=m.group(1),
                url=f"{self.base_url}/leilao/{m.group(1)}/detalhes",
                title=title,
                status_hint=self.status_from_text(status_el.get_text() if status_el else None),
                starts_at=parse_date_pt(date_el.get_text() if date_el else None),
                category=self.clean_text(cat_el.get_text()) if cat_el else None,
                judicial=judicial or bool(COURT_RE.search(title)),
            ))
        return out

    # ── pagina do pregao ─────────────────────────────────────────────

    async def scrape_auction(self, ref: AuctionRef) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        max_pages = int(self.cfg("max_pages", 10))
        ctx: Optional[AuctionContext] = None
        for page in range(1, max_pages + 1):
            url = ref.url if page == 1 else f"{ref.url}?page={page}"
            html = await self.fetch(url)
            self.stats.pages += 1
            if ctx is None:
                ctx = self.parse_auction_page(html, ref)
            lots = self.parse_lots(html, ctx)
            items.extend(lots)
            if not lots or not self._has_next(html):
                break
            if page == max_pages:
                self.stats.mark_partial(f"pregao {ref.external_id}: parou em {max_pages} paginas de lotes com mais disponiveis")
                break
            await self.delay()
        return items

    def parse_auction_page(self, html: str, ref: AuctionRef) -> AuctionContext:
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.select_one("h1")
        title = self.clean_text(h1.get_text()) if h1 else ref.title

        details: dict[str, str] = {}
        for item in soup.select(".auction-details-list .item"):
            label = item.select_one("label")
            value = item.select_one("span")
            if label and value:
                details[self.clean_text(label.get_text()).lower()] = self.clean_text(value.get_text(" "))
        groups: dict[str, str] = {}
        for group in soup.select(".text-groups .group"):
            label = group.select_one("label")
            if label:
                key = self.clean_text(label.get_text()).lower()
                label.extract()
                groups[key] = self.clean_text(group.get_text(" "))
        observations = groups.get("observações") or groups.get("observacoes") or ""

        starts_at = parse_date_pt(details.get("data")) or ref.starts_at
        category = details.get("categoria") or ref.category
        badges = " ".join(self.clean_text(b.get_text()) for b in soup.select(".title-wrapper .badge"))
        praca_kind = self._praca_kind(f"{title} {badges}")
        judicial = ref.judicial or bool(COURT_RE.search(title))

        sessions, price_second = self._sessions_from_observations(observations, praca_kind)
        if not sessions:
            sessions = [ScrapedSession(kind=praca_kind, starts_at=starts_at, ends_at=starts_at)]

        committer = None
        if judicial:
            # A vara e' o comitente do judicial; o sufixo "- 1ª PRAÇA" e' da sessao, nao do orgao.
            committer = self.clean_text(re.sub(r"\s*[-–]\s*[12]\s*[ªa°º]?\s*PRA[ÇC]A\s*$", "", title, flags=re.I)) or None

        auction = ScrapedAuction(
            external_id=ref.external_id,
            title=title,
            # Leiloeiro publico oficial e matricula publicados em /sobre-nos (17/10/2026).
            auctioneer_name="Gian Braggio — Parque dos Leilões",
            auctioneer_registration="Matrícula 51/11 — JUCIS-DF",
            committer_name=committer,
            modality=None,  # vem do badge do lote
            auction_type="judicial" if judicial else "extrajudicial",
            official_url=ref.url,
            sessions=sessions,
        )
        city, state, location_text = self._location_from_visitation(groups.get("visitação") or groups.get("visitacao"))
        extra: dict[str, Any] = {}
        m = re.search(r"PROCESSO\s*N?[ºo°]?\s*:?\s*([\d\.\-]{15,30})", observations, re.I)
        if m:
            extra["processo"] = m.group(1)
        return AuctionContext(
            auction=auction, category=category, city=city, state=state, location_text=location_text,
            price_second=price_second, praca_kind=praca_kind, extra=extra,
        )

    @staticmethod
    def _praca_kind(text: str) -> str:
        m = PRACA_RE.search(text or "")
        if not m:
            return "unica"
        return "1a_praca" if m.group(1) == "1" else "2a_praca"

    def _sessions_from_observations(self, text: str | None, praca_kind: str) -> tuple[list[ScrapedSession], Optional[Decimal]]:
        """Judiciais: 'AVALIAÇÃO : R$ 5.000,00 - 1ª PRAÇA 09/11/2026 ÀS 14H00 ... 2ª PRAÇA ...'."""
        if not text:
            return [], None
        found: dict[str, ScrapedSession] = {}
        for m in PRACA_OBS_RE.finditer(text):
            kind = "1a_praca" if m.group(2) == "1" else "2a_praca"
            value = self.parse_brl(re.sub(r"\s+", "", m.group(1)))
            when = self.parse_datetime_br(f"{m.group(3)} {m.group(4) or 0}:{m.group(5) or '00'}")
            found[kind] = ScrapedSession(kind=kind, starts_at=when, ends_at=when, min_bid=value)
        if not found:
            return [], None
        sessions = [found[k] for k in ("1a_praca", "2a_praca") if k in found]
        second = found.get("2a_praca")
        # Na 1ª praca o valor da 2ª e' o "preco se nao vender agora"; na 2ª
        # praca ja' nao ha' proxima.
        price_second = second.min_bid if (second and praca_kind == "1a_praca") else None
        return sessions, price_second

    def _location_from_visitation(self, text: str | None) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """'... LOTE 07, TAGUATINGA – BRASÍLIA/DF, NO HORÁRIO ...' -> cidade/UF do patio."""
        if not text:
            return None, None, None
        m = re.search(r"ENDERE[ÇC]O\s*:?\s*(.{10,160}?)(?:,?\s*NO HOR[ÁA]RIO|\.\s|$)", text, re.I)
        location_text = self.clean_text(m.group(1)) if m else None
        city = state = None
        for cm in re.finditer(r"([A-ZÀ-Ü][A-ZÀ-Üa-zà-ü\.]*(?:\s+[A-ZÀ-Ü][A-ZÀ-Üa-zà-ü\.]*){0,3})\s*/\s*([A-Z]{2})\b", text):
            city, state = self.parse_city_state(f"{cm.group(1)}/{cm.group(2)}")
        return self.reject_unknown(city), self.reject_unknown(state), location_text

    # ── lotes ────────────────────────────────────────────────────────

    def parse_lots(self, html: str, ctx: AuctionContext) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        # O detalhe de lote tambem usa `.auction-lot-card` em "Proximos lotes";
        # na pagina do pregao a lista fica na secao de lotes.
        scope = soup.select_one(".auction-lots-section") or soup
        for card in scope.select(".auction-lot-card"):
            try:
                item = self._parse_card(card, ctx)
                if item:
                    out.append(item)
            except Exception as exc:  # um card quebrado nao derruba a pagina
                self.stats.errors += 1
                logger.debug("[Parque] card ignorado: %s", exc)
        return out

    def _parse_card(self, card, ctx: AuctionContext) -> Optional[ScrapedItem]:
        link = card.select_one("a[href*='/lote/']")
        m = re.search(r"/leilao/(\d+)/lote/(\d+)", link.get("href", "")) if link else None
        if not m:
            return None
        lot_id = m.group(2)
        url = self.strip_tracking(self.abs_url(link["href"]))

        name_el = card.select_one(".card-body .name")
        title = self.clean_text(name_el.get_text()) if name_el else ""
        if not title:
            return None

        nr_el = card.select_one(".badge-nr-lot b")
        lot_number = self.clean_text(nr_el.get_text()) if nr_el else None
        type_el = card.select_one(".badge-type")
        modality = self._modality(type_el.get_text() if type_el else None)

        status_el = card.select_one(".lot-status-color")
        status_text = self.clean_text(status_el.get_text()) if status_el else ""
        status_id = status_el.get("data-lot-status-id") if status_el else None
        status_hint = self._lot_status(status_text, status_id, status_el.get("class") if status_el else None)

        img = card.select_one(".thumbnail img")
        thumb = self.reject_placeholder(img.get("src")) if img else None
        image_url = self._full_image(thumb)
        category_hint = self._category_hint(thumb, ctx.category)

        info = card.select_one(".comments-text")
        description = None
        if info:
            label = info.select_one("label")
            if label:
                label.extract()
            description = self.clean_text(info.get_text(" ")) or None

        auction = ctx.auction_copy()
        auction.modality = auction.modality or modality

        raw: dict[str, Any] = {
            "pregao": ctx.auction.title,
            "categoria_pregao": ctx.category,
            "status_lote": status_text or None,
            "status_lote_id": status_id,
            "modalidade": modality,
            "praca": ctx.praca_kind,
            "comitente": self._committer_from_description(description),
        }
        raw.update(ctx.extra)
        raw = {k: v for k, v in raw.items() if v not in (None, "")}

        return ScrapedItem(
            external_id=lot_id,
            title=title,
            official_url=url,
            price=None,  # so' no detalhe
            price_kind="lance_inicial",
            price_second=ctx.price_second,
            lot_number=lot_number,
            city=ctx.city or self.cfg("default_city", self.default_config["default_city"]) or None,
            state=ctx.state or self.cfg("default_state", self.default_config["default_state"]) or None,
            location_text=ctx.location_text,
            image_url=image_url,
            images=[image_url] if image_url else [],
            description=description,
            raw_attributes=raw,
            category_hint=category_hint,
            status_hint=status_hint,
            auction=auction,
            raw_payload=str(card),
        )

    @staticmethod
    def _modality(text: str | None) -> Optional[str]:
        t = (text or "").lower()
        if "online" in t and "presencial" in t:
            return "hibrido"
        if "online" in t:
            return "online"
        if "presencial" in t:
            return "presencial"
        return None

    @classmethod
    def _lot_status(cls, text: str, status_id: str | None, classes: list[str] | None) -> Optional[str]:
        t = (text or "").lower()
        if "cancelado" in t or "canceled" in (classes or []):
            return "withdrawn"
        if status_id in LOT_STATUS_MAP:
            return LOT_STATUS_MAP[status_id]
        return cls.status_from_text(t)

    @staticmethod
    def _full_image(thumb: str | None) -> Optional[str]:
        # `thumb-<hash>.webp` e' a miniatura do card; sem o prefixo e' a foto do slider.
        if not thumb:
            return None
        return re.sub(r"/thumb-([0-9a-f]{32}\.\w+)$", r"/\1", thumb)

    @staticmethod
    def _category_hint(image_url: str | None, auction_category: str | None) -> Optional[str]:
        m = re.search(r"/storage/([a-z-]+)/", image_url or "")
        if m and m.group(1) in STORAGE_CATEGORY:
            return STORAGE_CATEGORY[m.group(1)]
        cat = (auction_category or "").lower()
        if "veic" in cat or "veíc" in cat:
            return "veiculos"
        if "imov" in cat or "imóv" in cat:
            return "imoveis"
        if "equipamento" in cat or "maquina" in cat or "máquina" in cat:
            return "equipamentos"
        return cat or None

    @staticmethod
    def _committer_from_description(description: str | None) -> Optional[str]:
        """'(SANTANDER) *FINANCIE...' -> 'SANTANDER'. So' siglas/razoes em
        caixa alta entre parenteses no inicio; nunca nome de pessoa (RN-009)."""
        m = re.match(r"\(\s*([A-Z0-9][A-Z0-9 \.&\-]{1,40})\s*\)", description or "")
        return m.group(1).strip() if m else None

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")

        data: dict[str, Any] = {}
        holder = soup.select_one("[data-json='auctionLot']")
        if holder:
            try:
                data = json.loads(holder.get_text(strip=True))
            except ValueError:
                data = {}

        price = self.parse_brl(data.get("min_bid_value"))
        bids: dict[str, str] = {}
        for bid in soup.select(".bids-summary .bid-item[data-name]"):
            bids[bid["data-name"]] = bid.get("data-value") or ""
        if price is None and bids.get("min_bid_value"):
            price = self.parse_brl(bids["min_bid_value"])
        if price is not None:
            item.price = price
            item.price_kind = "lance_inicial"
        highest = self.parse_brl(bids.get("highest_bid")) if bids.get("highest_bid") else None
        if highest is not None:
            item.raw_attributes["maior_lance"] = str(highest)
        if data.get("increment_value"):
            item.raw_attributes["incremento"] = str(self.parse_brl(data["increment_value"]) or "")

        # Status do detalhe e' mais fresco que o do card. Encerrado com lance
        # e' vendido ("Homologado"); encerrado sem lance fica "closed".
        status_id = str(data.get("status_id") or "")
        if status_id:
            hint = LOT_STATUS_MAP.get(status_id) or self.status_from_text(data.get("status_name"))
            abbrev = (data.get("name_abbrev") or "").lower()
            if hint == "closed" and (highest is not None or "homolog" in abbrev or "arremat" in abbrev):
                hint = "sold"
            if item.status_hint != "withdrawn" and hint:
                item.status_hint = hint
            item.raw_attributes["status_detalhe"] = data.get("status_name")

        started = self.parse_datetime_br(data.get("started_at"))
        ended = self.parse_datetime_br(data.get("ended_at"))
        if started:
            item.raw_attributes["abertura_lances"] = started.isoformat()
        if item.auction:
            for badge in soup.select(".header-section .badges .badge"):
                mod = self._modality(self.clean_text(badge.get_text()))
                if mod:
                    item.auction.modality = mod
            own = next((s for s in item.auction.sessions if s.kind == item.raw_attributes.get("praca")), None)
            if own is None and item.auction.sessions:
                own = item.auction.sessions[0]
            if own is not None and ended:
                own.ends_at = ended
                own.starts_at = own.starts_at or ended
                if own.min_bid is None:
                    own.min_bid = price

        fields: dict[str, str] = {}
        for tr in soup.select(".accordions-section tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                key = self.clean_text(tds[0].get_text()).rstrip(":").lower()
                fields[key] = self.clean_text(tds[1].get_text(" "))
        self._apply_fields(item, fields)

        acessorios = [self.clean_text(li.get_text()) for li in soup.select(".accordions-section .optionals li")]
        acessorios = [a for a in acessorios if a]
        if acessorios:
            item.raw_attributes["acessorios"] = ", ".join(acessorios)
        docs = [self.clean_text(a.get_text()) for a in soup.select(".documents-list a")]
        docs = [d for d in docs if d]
        if docs:
            item.raw_attributes["documentos"] = ", ".join(docs)

        # Imoveis: endereco e mapa. Veiculos: nada alem do patio (contexto do pregao).
        map_el = soup.select_one(".map[data-address]")
        if map_el and map_el.get("data-address"):
            address = re.sub(r",?\s*Brasil\s*$", "", self.clean_text(map_el["data-address"]))
            city, state = self.parse_city_state(address)
            if state:
                item.city, item.state, item.location_text = city, state, address

        imgs: list[str] = []
        for img in soup.select("#photos-main-slider img[src], #photos-thumbs-slider img[src]"):
            src = img["src"]
            # O primeiro slide costuma ser o banner do vendedor (storage/auction-sellers/): nao e' foto do bem.
            if "/storage/" not in src or "auction-sellers" in src or src in imgs:
                continue
            imgs.append(src)
        if imgs:
            item.images = imgs[:12]
            item.image_url = imgs[0]

        desc_parts = [item.description] if item.description else []
        if acessorios:
            desc_parts.append("Acessórios: " + ", ".join(acessorios) + ".")
        if desc_parts:
            item.description = " ".join(desc_parts)
        item.raw_payload = (item.raw_payload or "") + "\n<!-- detail -->\n" + (holder.get_text(strip=True) if holder else "")

    def _apply_fields(self, item: ScrapedItem, fields: dict[str, str]) -> None:
        raw = item.raw_attributes
        desc = self.reject_unknown(fields.get("descrição") or fields.get("descricao"))
        if desc and desc != item.description:
            item.description = desc
        marca = self.reject_unknown(fields.get("marca"))
        if marca:
            # "I/BMW": o prefixo I/ e' "importado" na tabela do Detran.
            raw["marca"] = re.sub(r"^I/\s*", "", marca).title()
            if marca.upper().startswith("I/"):
                raw["importado"] = True
        modelo = self.reject_unknown(fields.get("modelo"))
        if modelo:
            raw["modelo"] = modelo.title()
        ano = fields.get("ano") or ""
        m = re.match(r"(\d{4})\s*/\s*(\d{4})", ano)
        if m:
            raw["ano_fabricacao"], raw["ano_modelo"] = int(m.group(1)), int(m.group(2))
        elif re.match(r"\d{4}$", ano):
            raw["ano_modelo"] = int(ano)
        km = fields.get("quilometragem") or ""
        if re.search(r"\d", km):
            raw["km"] = int(re.sub(r"\D", "", km))
        for src, dst in (("cor", "cor"), ("combustível", "combustivel"), ("combustivel", "combustivel")):
            v = self.reject_unknown(fields.get(src))
            if v:
                raw[dst] = v.title()
        if not raw.get("combustivel"):
            # Quando a tabela diz "-", o leiloeiro costuma escrever na descricao
            # ("COMBUSTÍVEL: GASOLINA/ELETRICO").
            m = re.search(r"COMBUST[IÍ]VEL\s*:\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ/]+)", item.description or "", re.I)
            if m:
                raw["combustivel"] = m.group(1).title()
        if fields.get("sinistro"):
            raw["sinistro"] = fields["sinistro"].strip().lower().startswith("s")
        vm = fields.get("valor de mercado") or ""
        if "R$" in vm:
            raw["valor_mercado"] = str(self.parse_brl(vm) or "")
            m = re.search(r"/\s*([a-zç]+\s+de\s+\d{4})", vm, re.I)
            if m:
                raw["valor_mercado_ref"] = m.group(1)
        if fields.get("título") and not item.title:
            item.title = fields["título"]
