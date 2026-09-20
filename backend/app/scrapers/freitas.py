"""Freitas Leiloeiro — ASP.NET MVC. A listagem e' carregada por AJAX em
`GET /Leiloes/PesquisarLotes?Categoria=1&PageNumber=N&TopRows=60`, que
devolve uma partial view com cards `.cardlote`. Categoria 1 = veiculos.

A descricao do card ja' vem com a placa mascarada pela propria fonte
("PLACA: D__-___6"). Detalhe traz leiloeiro, modalidade, local, comissao e
observacoes (avarias).

Verificado em 18/09/2026.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.freitas")

ORIGEM_MAP = {
    "financeira": "financeira", "banco": "financeira", "seguradora": "seguradora",
    "locadora": "locadora", "frota": "frota", "judicial": "judicial",
}


class FreitasScraper(BaseScraper):
    display_name = "Freitas Leiloeiro"
    default_config = {
        "categoria": 1,
        "verify_ssl": False,  # cadeia de certificado incompleta no servidor deles (set/2026)
        "top_rows": 60,
        "max_pages": 30,
        "fetch_details": True,
        "max_details_per_run": 60,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.freitasleiloeiro.com.br"

    def _ajax_headers(self) -> dict[str, str]:
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/Leiloes/Pesquisar?Categoria={self.cfg('categoria', 1)}",
            "Accept": "text/html, */*; q=0.01",
        }

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        top = int(self.cfg("top_rows", 60))
        max_pages = int(self.cfg("max_pages", 30))
        for page in range(1, max_pages + 1):
            params = {
                "Categoria": self.cfg("categoria", 1),
                "PageNumber": page,
                "TopRows": top,
                "ClienteSclId": 0,
            }
            try:
                html = await self.fetch(f"{self.base_url}/Leiloes/PesquisarLotes", params=params, headers=self._ajax_headers())
            except Exception as exc:
                self.stats.errors += 1
                logger.warning("[Freitas] falha na pagina %d: %s", page, exc)
                break
            self.stats.pages += 1
            if "Nenhum lote localizado" in html or "Erro ao tentar" in html:
                break
            parsed = self.parse_listing(html)
            logger.info("[Freitas] pagina %d: %d cards", page, len(parsed))
            if not parsed:
                break
            items.extend(parsed)
            if len(parsed) < top:
                break
            if page == max_pages:
                self.stats.mark_partial(f"parou em {max_pages} paginas com a ultima cheia ({top} lotes)")
                break
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
                    logger.warning("[Freitas] detalhe falhou %s: %s", it.official_url, exc)
        return items

    # ── listagem ─────────────────────────────────────────────────────

    def parse_listing(self, html: str) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        for card in soup.select(".cardlote"):
            try:
                item = self._parse_card(card)
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Freitas] card ignorado: %s", exc)
        return out

    def _parse_card(self, card) -> Optional[ScrapedItem]:
        link = card.select_one("a[href*='LoteDetalhes']")
        if not link:
            return None
        href = link.get("href", "")
        qs = parse_qs(urlsplit(href).query)
        leilao_id = (qs.get("leilaoId") or [None])[0]
        lote_num = (qs.get("loteNumero") or [None])[0]
        if not leilao_id or not lote_num:
            return None
        url = self.abs_url(href)

        desc_el = card.select_one(".cardLote-descVeic")
        title = self.clean_text(desc_el.get_text()) if desc_el else f"Lote {lote_num}"
        img = card.select_one("img.cardLote-img")
        image_url = img.get("src") if img else None

        date_spans = [self.clean_text(s.get_text()) for s in card.select(".cardLote-data span")]
        starts_at = self.parse_datetime_br(" ".join(date_spans)) if date_spans else None

        price_el = card.select_one(".cardLote-vlr")
        price = self.parse_brl(price_el.get_text()) if price_el else None
        label_el = card.select_one(".cardLote-lance")
        price_kind = "lance_inicial"
        if label_el and "atual" in label_el.get_text().lower():
            price_kind = "lance_atual"

        opts = [b.get("title") or self.clean_text(b.get_text()) for b in card.select(".cardLote-opc button")]
        client_el = card.select_one(".cardLote-details span")
        client_type = self.clean_text(client_el.get_text()).lower() if client_el else ""
        origem = next((v for k, v in ORIGEM_MAP.items() if k in client_type), None)

        status_el = card.select_one(".cardLote-btn")
        status_hint = self.status_from_text(status_el.get_text() if status_el else None)

        lot_el = card.select_one(".cardLote-lote")
        lot_number = self.clean_text(lot_el.get_text()).lstrip("0") if lot_el else str(lote_num)

        auction = ScrapedAuction(
            external_id=str(leilao_id),
            title=f"Leilão {leilao_id}" + (f" — {starts_at:%d/%m/%Y}" if starts_at else ""),
            auction_type="extrajudicial",
            modality=None,
            official_url=f"{self.base_url}/Leiloes/Pesquisar?Categoria={self.cfg('categoria', 1)}",
            sessions=[ScrapedSession(kind="unica", starts_at=starts_at)],
            committer_name=client_type.upper() or None,
        )
        return ScrapedItem(
            external_id=f"{leilao_id}-{lote_num}",
            title=title,
            official_url=url,
            price=price,
            price_kind=price_kind,
            lot_number=lot_number or str(lote_num),
            image_url=image_url,
            images=[image_url] if image_url else [],
            description=title,
            raw_attributes={"opcionais": ", ".join(o for o in opts if o), "origem": origem, "tipo_comitente": client_type or None},
            category_hint="veiculos",
            status_hint=status_hint,
            auction=auction,
            raw_payload=str(card),
        )

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        info: dict[str, str] = {}
        for tr in soup.select("table tr"):
            th, td = tr.find("th"), tr.find("td")
            if th and td:
                info[self.clean_text(th.get_text()).rstrip(":").lower()] = self.clean_text(td.get_text(" "))

        parts: list[str] = []
        full = soup.find(string=re.compile(r"Descri[cç][aã]o completa", re.I))
        if full and full.parent:
            container = full.parent.find_parent("div")
            if container:
                parts.append(self.clean_text(container.get_text(" ")))
        # Observacoes/avarias: bloco em caixa alta com "/" separando, apos "condições"
        obs = soup.find(string=re.compile(r"Leia atentamente", re.I))
        if obs and obs.parent:
            nxt = obs.parent.find_next(["p", "div"])
            if nxt:
                txt = self.clean_text(nxt.get_text(" "))
                if txt and "Html.Raw" not in txt:
                    parts.append(txt)
        important = soup.find(string=re.compile(r"Informa[cç][oõ]es importantes", re.I))
        if important and important.parent:
            ul = important.parent.find_next("ul")
            if ul:
                parts.append("Informações: " + "; ".join(self.clean_text(li.get_text(" ")) for li in ul.select("li")))
        if parts:
            item.description = "\n".join(p for p in parts if p)

        local = info.get("local do leilão") or info.get("local do leilao")
        if local:
            item.location_text = local
            city, state = self.parse_city_state(local)
            item.city, item.state = item.city or city, item.state or state
        page_text = self.clean_text(soup.get_text(" "))
        m = re.search(r"(\d+(?:,\d+)?)\s*%\s*referente [àa] comiss", page_text, re.I)
        if m:
            item.raw_attributes["comissao_pct"] = m.group(1).replace(",", ".")
        if item.auction:
            if info.get("leiloeiro"):
                item.auction.auctioneer_name = info["leiloeiro"]
            mod = (info.get("modalidade") or "").lower()
            if mod:
                item.auction.modality = "hibrido" if ("online" in mod and "presencial" in mod) else ("online" if "online" in mod else "presencial")
            if info.get("abertura p/ lances"):
                opened = self.parse_datetime_br(info["abertura p/ lances"])
                if opened and item.auction.sessions:
                    item.auction.sessions[0].ends_at = item.auction.sessions[0].starts_at
                    item.raw_attributes["abertura_lances"] = opened.isoformat()
        imgs = list(dict.fromkeys(re.findall(r"https://cdn\d*\.freitasleiloeiro\.com\.br/LEILOES/\d+/FOTOS/[^\"' ]+\.(?:JPG|jpg|jpeg|png)", html)))
        if imgs:
            item.images = imgs[:12]
            item.image_url = item.image_url or imgs[0]
