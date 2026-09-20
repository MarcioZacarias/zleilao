"""Mega Leilões — HTML renderizado no servidor, cards em `.card` dentro de
`div[data-key]`. Paginacao via `?pagina=N`. robots.txt permite tudo.

Card (listagem) -> titulo, preco 1a/2a praca, datas das pracas, status,
cidade/UF, tipo (Judicial/Extrajudicial), imagem.
Detalhe (opcional) -> descricao, leiloeiro, localizacao, vara, imagens.

Verificado em 18/09/2026 contra https://www.megaleiloes.com.br/veiculos.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.megaleiloes")


class MegaLeiloesScraper(BaseScraper):
    display_name = "Mega Leilões"
    default_config = {
        "pages": ["/veiculos"],
        "max_pages": 10,
        "fetch_details": True,
        "max_details_per_run": 60,
    }

    @property
    def default_base_url(self) -> str:
        return "https://www.megaleiloes.com.br"

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        max_pages = int(self.cfg("max_pages", 10))
        for path in self.cfg("pages", ["/veiculos"]):
            for page in range(1, max_pages + 1):
                url = self.abs_url(path)
                sep = "&" if "?" in url else "?"
                if page > 1:
                    url = f"{url}{sep}pagina={page}"
                try:
                    html = await self.fetch(url)
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Mega] falha na pagina %s: %s", url, exc)
                    break
                self.stats.pages += 1
                parsed = self.parse_listing(html, path)
                logger.info("[Mega] %s pagina %d: %d cards", path, page, len(parsed))
                items.extend(parsed)
                if not parsed or not self._has_next_page(html, page):
                    break
                if page == max_pages:
                    # Ha' proxima pagina e o limite acabou: catalogo nao foi visto por inteiro.
                    self.stats.mark_partial(f"parou em {max_pages} paginas de {path} com mais paginas disponiveis")
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
                    logger.warning("[Mega] detalhe falhou %s: %s", it.official_url, exc)
        return items

    # ── listagem ─────────────────────────────────────────────────────

    @staticmethod
    def _has_next_page(html: str, page: int) -> bool:
        return f"pagina={page + 1}" in html

    def parse_listing(self, html: str, path: str = "") -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        out: list[ScrapedItem] = []
        for wrapper in soup.select("div[data-key]"):
            card = wrapper.select_one(".card")
            if not card:
                continue
            try:
                item = self._parse_card(wrapper, card, path)
                if item:
                    out.append(item)
            except Exception as exc:  # um card quebrado nao derruba a pagina
                self.stats.errors += 1
                logger.debug("[Mega] card ignorado: %s", exc)
        return out

    def _parse_card(self, wrapper, card, path: str) -> Optional[ScrapedItem]:
        external_id = wrapper.get("data-key")
        title_a = card.select_one(".card-title")
        if not external_id or not title_a:
            return None
        title = self.clean_text(title_a.get_text())
        url = self.strip_tracking(self.abs_url(title_a.get("href", "")))

        img_a = card.select_one(".card-image")
        image_url = self.reject_placeholder(img_a.get("data-bg") if img_a else None)

        price_el = card.select_one(".card-price")
        price = self.parse_brl(price_el.get_text()) if price_el else None

        loc_el = card.select_one(".card-locality")
        city, state = self.parse_city_state(loc_el.get("title") or loc_el.get_text()) if loc_el else (None, None)
        city, state = self.reject_unknown(city), self.reject_unknown(state)

        status_el = card.select_one(".card-status")
        status_hint = self.status_from_text(status_el.get_text() if status_el else None)

        code_el = card.select_one(".card-number")
        lot_code = self.clean_text(code_el.get_text()) if code_el else None
        batch_el = card.select_one(".card-batch-number")
        lot_number = self.clean_text(batch_el.get_text()).replace("Lote", "").strip() if batch_el else None

        type_el = card.select_one(".card-instance-title a")
        auction_type = None
        if type_el:
            t = self.clean_text(type_el.get_text()).lower()
            auction_type = "judicial" if "judicial" in t and "extra" not in t else ("extrajudicial" if "extra" in t else None)

        sessions: list[ScrapedSession] = []
        price_second = None
        for inst in card.select(".instance"):
            date_el = inst.select_one("[class*=instance-date]")
            val_el = inst.select_one(".card-instance-value")
            if not date_el:
                continue
            label = self.clean_text(date_el.get_text())
            kind = "1a_praca" if "1" in label.split(":")[0] else ("2a_praca" if "2" in label.split(":")[0] else "unica")
            starts = self.parse_datetime_br(label)
            min_bid = self.parse_brl(val_el.get_text()) if val_el else None
            sessions.append(ScrapedSession(kind=kind, starts_at=starts, min_bid=min_bid))
            if kind == "2a_praca" and min_bid is not None:
                price_second = min_bid
        if not sessions:
            date_el = card.select_one("[class*=instance-date]")
            if date_el:
                sessions.append(ScrapedSession(kind="unica", starts_at=self.parse_datetime_br(date_el.get_text())))

        gavel = card.select_one(".card-gavet-link")
        auction_ext = None
        if gavel and gavel.get("href"):
            m = re.search(r"/auditorio/(\d+)/", gavel["href"])
            if m:
                auction_ext = m.group(1)
        auction = ScrapedAuction(
            external_id=auction_ext or f"lot-{external_id}",
            auction_type=auction_type,
            modality="online",
            sessions=sessions,
            official_url=url,
        )

        # Dica de categoria pela URL do lote: /veiculos/carros/sp/...
        category_hint = None
        m = re.search(r"megaleiloes\.com\.br/veiculos/([a-z-]+)/", url)
        if m:
            category_hint = m.group(1)

        return ScrapedItem(
            external_id=external_id,
            title=title,
            official_url=url,
            price=price,
            price_kind="lance_inicial",
            price_second=price_second,
            lot_number=lot_number,
            city=city,
            state=state,
            image_url=image_url,
            images=[image_url] if image_url else [],
            raw_attributes={"codigo": lot_code, "tipo_leilao": auction_type},
            category_hint=category_hint,
            status_hint=status_hint,
            auction=auction,
            raw_payload=str(wrapper),
        )

    # ── detalhe ──────────────────────────────────────────────────────

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        desc = soup.select_one("#tab-description")
        if desc:
            item.description = self.clean_text(desc.get_text(" "))

        fields: dict[str, str] = {}
        for block in soup.select("div.item"):
            header = block.select_one(".header")
            value = block.select_one(".value")
            if header and value:
                fields[self.clean_text(header.get_text()).lower()] = self.clean_text(value.get_text(" "))

        if fields.get("localização"):
            item.location_text = fields["localização"]
            if not item.city or not item.state:
                city, state = self.parse_city_state(fields["localização"])
                item.city, item.state = item.city or city, item.state or state
        if item.auction:
            leiloeiro = fields.get("leiloeiro")
            if leiloeiro:
                name = re.split(r"\s+JUC[A-Z]{2,4}\b", leiloeiro)[0]
                item.auction.auctioneer_name = self.clean_text(name)[:200]
                m = re.search(r"(JUC[A-Z]{2,3}\s*N?º?\s*[\d\.]+)", leiloeiro, re.I)
                if m:
                    item.auction.auctioneer_registration = m.group(1)
            vara = fields.get("vara") or fields.get("forum")
            if vara:
                item.auction.committer_name = vara
                item.auction.auction_type = item.auction.auction_type or "judicial"
            if vara and not item.auction.title:
                item.auction.title = f"Leilão judicial — {vara}"[:300]
        if fields.get("valor de avaliação"):
            item.raw_attributes["valor_avaliacao"] = str(self.parse_brl(fields["valor de avaliação"]) or "")
        # Partes do processo (autor/reu) sao dados pessoais: NAO armazenar (RN-009).

        imgs: list[str] = []
        for m in re.finditer(r"https://cdn\d*\.megaleiloes\.com\.br/batches/[^\"' ]+?_(?:670x380|1024x768)\.jpg", html):
            if m.group(0) not in imgs:
                imgs.append(m.group(0))
        if imgs:
            item.images = imgs[:12]
            item.image_url = item.image_url or imgs[0]
        item.raw_payload = (item.raw_payload or "") + "\n<!-- detail -->\n" + (str(desc) if desc else "")
