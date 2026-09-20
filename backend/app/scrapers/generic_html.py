"""Parser generico dirigido por configuracao (seletores CSS) — permite
cadastrar um leiloeiro pelo admin sem escrever codigo.

Dois modos, escolhidos pela presenca de `auction_list`:

**Lista direta** — uma pagina lista os lotes, com paginacao por query string:

```json
{
  "list_urls": ["/lotes/veiculos"],
  "pagination": {"param": "pagina", "max_pages": 5},
  "item_selector": ".card-lote",
  "fields": {
    "external_id": {"selector": "a", "attr": "href", "regex": "/lote/(\\\\d+)"},
    "title":       {"selector": ".titulo"},
    "url":         {"selector": "a", "attr": "href"},
    "price":       {"selector": ".valor"},
    "image":       {"selector": "img", "attr": "src"},
    "location":    {"selector": ".cidade"},
    "date":        {"selector": ".data"},
    "status":      {"selector": ".situacao"}
  },
  "category_hint": "veiculos",
  "auction_type": "extrajudicial"
}
```

**Duas etapas** — a home lista PREGOES e cada pregao lista os lotes. E' a
estrutura mais comum entre leiloeiros de porte medio, e sem ela o parser
generico nao serviria para a maioria deles:

```json
{
  "auction_list": {
    "url": "/leiloes",
    "item_selector": ".auction-card",
    "link": {"selector": "a[href*='/leilao/']", "attr": "href"},
    "id_regex": "/leilao/(\\\\d+)",
    "title": {"selector": ".name"},
    "date": {"selector": ".date"},
    "max_auctions": 20
  },
  "item_selector": ".auction-lot-card",
  "fields": { ... }
}
```
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

    # ── extração por seletor ─────────────────────────────────────────

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

    # ── ciclo ────────────────────────────────────────────────────────

    async def scrape(self) -> list[ScrapedItem]:
        if self.cfg("auction_list"):
            items = await self._scrape_two_stage()
        else:
            items = await self._scrape_flat()

        detail_cfg = self.cfg("detail") or {}
        if self.fetch_details and detail_cfg.get("description_selector"):
            fetched = 0
            for it in items:
                if fetched >= self.max_details:
                    self.stats.notes.append(f"limite de {self.max_details} detalhes atingido")
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

    async def _scrape_flat(self) -> list[ScrapedItem]:
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
                if page == max_pages:
                    self.stats.mark_partial(f"parou em {max_pages} paginas de {path}")
                await self.delay()
        return items

    async def _scrape_two_stage(self) -> list[ScrapedItem]:
        """Home lista pregões; cada pregão lista os lotes."""
        cfg = self.cfg("auction_list") or {}
        try:
            html = await self.fetch(self.abs_url(cfg.get("url", "/")))
        except Exception as exc:
            self.stats.errors += 1
            logger.warning("[Generic] falha na lista de leiloes: %s", exc)
            return []
        self.stats.pages += 1

        auctions = self.parse_auction_list(html)
        limit = int(cfg.get("max_auctions", 20))
        if len(auctions) > limit:
            self.stats.mark_partial(f"{len(auctions)} leiloes encontrados, limite de {limit} por ciclo")
            auctions = auctions[:limit]
        logger.info("[Generic] %d leiloes para percorrer", len(auctions))

        items: list[ScrapedItem] = []
        for auction in auctions:
            try:
                await self.delay()
                lot_html = await self.fetch(auction["url"])
                self.stats.pages += 1
            except Exception as exc:
                self.stats.errors += 1
                logger.warning("[Generic] falha no leilao %s: %s", auction["url"], exc)
                continue
            got = self.parse_listing(lot_html, auction=auction)
            logger.debug("[Generic] leilao %s: %d lotes", auction["external_id"], len(got))
            items.extend(got)
        return items

    def parse_auction_list(self, html: str) -> list[dict]:
        cfg = self.cfg("auction_list") or {}
        soup = BeautifulSoup(html, "lxml")
        out: list[dict] = []
        seen: set[str] = set()
        for el in soup.select(cfg.get("item_selector", ".card")):
            href = self._extract(el, cfg.get("link") or {"selector": "a", "attr": "href"})
            if not href:
                continue
            url = self.strip_tracking(self.abs_url(href))
            ext = None
            if cfg.get("id_regex"):
                m = re.search(cfg["id_regex"], url)
                ext = m.group(1) if m and m.groups() else None
            ext = ext or re.sub(r"\W+", "-", url)[-80:]
            if ext in seen:
                continue
            seen.add(ext)
            out.append({
                "external_id": ext,
                "url": url,
                "title": self._extract(el, cfg.get("title")),
                "date": self._extract(el, cfg.get("date")),
                "modality": self._extract(el, cfg.get("modality")),
            })
        return out

    def parse_listing(self, html: str, auction: dict | None = None) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        fields: dict[str, Any] = self.cfg("fields") or {}
        out: list[ScrapedItem] = []
        for el in soup.select(self.cfg("item_selector", ".card")):
            try:
                item = self._parse_item(el, fields, auction)
                if item:
                    out.append(item)
            except Exception as exc:
                self.stats.errors += 1
                logger.debug("[Generic] item ignorado: %s", exc)
        return out

    def _parse_item(self, el, fields: dict, auction: dict | None) -> Optional[ScrapedItem]:
        title = self._extract(el, fields.get("title"))
        href = self._extract(el, fields.get("url"))
        if not title or not href:
            return None
        url = self.strip_tracking(self.abs_url(href))
        ext = self._extract(el, fields.get("external_id")) or re.sub(r"\W+", "-", url)[-120:]

        loc = self.reject_unknown(self._extract(el, fields.get("location")))
        city, state = self.parse_city_state(loc)
        city, state = self.reject_unknown(city), self.reject_unknown(state)
        image = self._extract(el, fields.get("image"))
        date_txt = self._extract(el, fields.get("date")) or (auction or {}).get("date")
        starts_at = self.parse_datetime_br(date_txt)

        if auction:
            sessions = [ScrapedSession(kind="unica", starts_at=starts_at)] if starts_at else []
            scraped_auction = ScrapedAuction(
                external_id=auction["external_id"],
                title=auction.get("title"),
                auction_type=self.cfg("auction_type"),
                modality=(auction.get("modality") or "").lower() or None,
                official_url=auction["url"],
                sessions=sessions,
            )
        else:
            sessions = [ScrapedSession(kind="unica", starts_at=starts_at)] if starts_at else []
            scraped_auction = ScrapedAuction(
                external_id=self._extract(el, fields.get("auction_id")) or f"lot-{ext}",
                auction_type=self.cfg("auction_type"),
                official_url=url,
                sessions=sessions,
            )

        return ScrapedItem(
            external_id=ext,
            title=title,
            official_url=url,
            price=self.parse_brl(self._extract(el, fields.get("price"))),
            lot_number=self._extract(el, fields.get("lot_number")),
            city=city, state=state, location_text=loc,
            image_url=self.reject_placeholder(self.abs_url(image) if image else None),
            images=[self.abs_url(image)] if image and self.reject_placeholder(image) else [],
            description=self._extract(el, fields.get("description")),
            category_hint=self.cfg("category_hint", "veiculos"),
            status_hint=self.status_from_text(self._extract(el, fields.get("status"))),
            auction=scraped_auction,
            raw_payload=str(el),
        )

    def enrich_from_detail(self, item: ScrapedItem, html: str) -> None:
        detail = self.cfg("detail") or {}
        soup = BeautifulSoup(html, "lxml")
        sel = detail.get("description_selector")
        if sel:
            el = soup.select_one(sel)
            if el:
                item.description = self.clean_text(el.get_text(" "))
        if detail.get("price_selector") and item.price is None:
            el = soup.select_one(detail["price_selector"])
            if el:
                item.price = self.parse_brl(el.get_text())
        if detail.get("location_selector") and not item.city:
            el = soup.select_one(detail["location_selector"])
            if el:
                loc = self.reject_unknown(self.clean_text(el.get_text(" ")))
                item.location_text = loc or item.location_text
                city, state = self.parse_city_state(loc)
                item.city, item.state = self.reject_unknown(city), self.reject_unknown(state)
        if detail.get("images_regex"):
            imgs = list(dict.fromkeys(re.findall(detail["images_regex"], html)))
            if imgs:
                item.images = imgs[:12]
                item.image_url = item.image_url or imgs[0]
