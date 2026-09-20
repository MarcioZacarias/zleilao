"""Parser generico dirigido por configuracao (seletores CSS) — permite
cadastrar um leiloeiro simples pelo admin sem escrever codigo.

Exemplo de `config`:
{
  "list_urls": ["/lotes/veiculos"],
  "pagination": {"param": "pagina", "max_pages": 5},
  "item_selector": ".card-lote",
  "fields": {
    "external_id": {"selector": "a", "attr": "href", "regex": "/lote/(\\d+)"},
    "title":       {"selector": ".titulo"},
    "url":         {"selector": "a", "attr": "href"},
    "price":       {"selector": ".valor"},
    "image":       {"selector": "img", "attr": "src"},
    "location":    {"selector": ".cidade"},
    "date":        {"selector": ".data"},
    "status":      {"selector": ".situacao"},
    "lot_number":  {"selector": ".numero"},
    "description": {"selector": ".descricao"}
  },
  "detail": {"description_selector": "#descricao", "images_regex": "https://cdn\\.x\\.com/[^\"']+\\.jpg"},
  "category_hint": "veiculos",
  "auction_type": "extrajudicial"
}
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.generic")


class GenericHtmlScraper(BaseScraper):
    display_name = "Genérico (HTML por seletores)"
    default_config = {
        "list_urls": ["/"],
        "pagination": {"param": "pagina", "max_pages": 3},
        "item_selector": ".card",
        "fields": {
            "external_id": {"selector": "a", "attr": "href", "regex": r"(\d+)"},
            "title": {"selector": "a"},
            "url": {"selector": "a", "attr": "href"},
            "price": {"selector": ".price"},
            "image": {"selector": "img", "attr": "src"},
            "location": {"selector": ".location"},
            "date": {"selector": ".date"},
            "status": {"selector": ".status"},
        },
        "detail": {},
        "category_hint": "veiculos",
        "auction_type": "extrajudicial",
        "fetch_details": False,
    }

    @property
    def default_base_url(self) -> str:
        return self.cfg("base_url", "https://example.com")

    def _extract(self, el, spec: dict | None) -> Optional[str]:
        if not spec:
            return None
        target = el.select_one(spec["selector"]) if spec.get("selector") else el
        if target is None:
            return None
        val = target.get(spec["attr"]) if spec.get("attr") else target.get_text(" ")
        if isinstance(val, list):
            val = val[0] if val else None
        if val is None:
            return None
        val = self.clean_text(str(val))
        if spec.get("regex"):
            m = re.search(spec["regex"], val)
            val = m.group(1) if m and m.groups() else (m.group(0) if m else None)
        return val or None

    async def scrape(self) -> list[ScrapedItem]:
        items: list[ScrapedItem] = []
        pag = self.cfg("pagination") or {}
        max_pages = int(pag.get("max_pages", 1))
        for path in self.cfg("list_urls", ["/"]):
            for page in range(1, max_pages + 1):
                url = self.abs_url(path)
                if page > 1:
                    if pag.get("param"):
                        sep = "&" if "?" in url else "?"
                        url = f"{url}{sep}{pag['param']}={page}"
                    elif pag.get("path_template"):
                        url = self.abs_url(pag["path_template"].format(page=page, path=path))
                    else:
                        break
                try:
                    html = await self.fetch(url)
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Generic] falha em %s: %s", url, exc)
                    break
                self.stats.pages += 1
                parsed = self.parse_listing(html)
                if not parsed:
                    break
                items.extend(parsed)
                if page == max_pages and len(parsed) > 0:
                    self.stats.mark_partial(f"parou em {max_pages} paginas de {path}")
                await self.delay()
        if self.fetch_details and (self.cfg("detail") or {}).get("description_selector"):
            fetched = 0
            for it in items:
                if fetched >= self.max_details:
                    break
                try:
                    await self.delay()
                    self.enrich_from_detail(it, await self.fetch(it.official_url))
                    fetched += 1
                    self.stats.details += 1
                except Exception as exc:
                    self.stats.errors += 1
                    logger.warning("[Generic] detalhe falhou %s: %s", it.official_url, exc)
        return items

    def parse_listing(self, html: str) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        fields: dict[str, Any] = self.cfg("fields") or {}
        out: list[ScrapedItem] = []
        for el in soup.select(self.cfg("item_selector", ".card")):
            try:
                ext = self._extract(el, fields.get("external_id"))
                title = self._extract(el, fields.get("title"))
                href = self._extract(el, fields.get("url"))
                if not title or not href:
                    continue
                url = self.strip_tracking(self.abs_url(href))
                ext = ext or re.sub(r"\W+", "-", url)[-120:]
                loc = self._extract(el, fields.get("location"))
                city, state = self.parse_city_state(loc)
                date_txt = self._extract(el, fields.get("date"))
                image = self._extract(el, fields.get("image"))
                sessions = [ScrapedSession(kind="unica", starts_at=self.parse_datetime_br(date_txt))] if date_txt else []
                out.append(ScrapedItem(
                    external_id=ext,
                    title=title,
                    official_url=url,
                    price=self.parse_brl(self._extract(el, fields.get("price"))),
                    lot_number=self._extract(el, fields.get("lot_number")),
                    city=city, state=state, location_text=loc,
                    image_url=self.abs_url(image) if image else None,
                    images=[self.abs_url(image)] if image else [],
                    description=self._extract(el, fields.get("description")),
                    category_hint=self.cfg("category_hint", "veiculos"),
                    status_hint=self.status_from_text(self._extract(el, fields.get("status"))),
                    auction=ScrapedAuction(
                        external_id=self._extract(el, fields.get("auction_id")) or f"lot-{ext}",
                        auction_type=self.cfg("auction_type"),
                        sessions=sessions,
                        official_url=url,
                    ),
                    raw_payload=str(el),
                ))
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Generic] item ignorado: %s", exc)
        return out

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        detail = self.cfg("detail") or {}
        soup = BeautifulSoup(html, "lxml")
        sel = detail.get("description_selector")
        if sel:
            el = soup.select_one(sel)
            if el:
                item.description = self.clean_text(el.get_text(" "))
        if detail.get("images_regex"):
            imgs = list(dict.fromkeys(re.findall(detail["images_regex"], html)))
            if imgs:
                item.images = imgs[:12]
                item.image_url = item.image_url or imgs[0]
