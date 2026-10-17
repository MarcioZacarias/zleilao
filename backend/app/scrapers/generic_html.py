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

**Cada campo** (`fields`, `auction_list.*`, `page_fields`) e' um spec
`{"selector", "attr", "regex", "sub", "map"}`, aplicado nessa ordem:

- `selector`: CSS relativo ao card (ausente = o proprio card);
- `attr`: atributo a ler (ausente = texto);
- `regex`: fica so' o grupo 1 (ou a correspondencia inteira);
- `sub`: `[padrao, substituicao]` regex — ex.: miniatura `123p.jpeg` -> foto
  cheia `123.jpeg`;
- `map`: `{"texto": "valor"}` comparado sem acento nem caixa — ex.: `status`
  `{"em leilao": "open"}`, `category` `{"motocicleta": "motos"}`. Sem
  correspondencia o texto segue como veio.

**Extensoes** (todas opcionais; servem a qualquer fonte):

- `fields.end_date`, `auction_list.end_date`, `page_fields.end_date`:
  encerramento do pregao (`ends_at`), separado da abertura (`date`).
- `fields.category`: dica de categoria lida do card; sobrepoe `category_hint`
  (uma fonte que mistura motos, carros e moveis nao cabe numa dica unica).
- `page_fields`: campos lidos da PAGINA do pregao (etapa 2), nao do card —
  `title`, `date`, `end_date`, `modality`, `location`. Valem para todos os
  lotes dela e sobrepoem o que a lista de pregoes trouxe, que muitas vezes
  vem sem ano ("Encerra: 21/10 16:00") enquanto o cabecalho e' completo.
- Datas `dd/mm HH:MM` sem ano: assume o ano corrente ou, se a data ja' passou
  ha' mais de 30 dias, o proximo (a capa so' lista pregoes futuros).
- `default_state`: UF aplicada quando a fonte da' a cidade sem UF (leiloeiro
  de um estado so').
- `auction_type: "auto"`: `judicial` quando o titulo do pregao (ou o campo
  `auction_type` do card) cita vara, juizado, tribunal etc.; `extrajudicial`
  quando diz "extrajudicial"; senao `auction_type_default`.
- `detail.images_regex`: URLs relativas viram absolutas e o placeholder da
  fonte e' descartado, como ja' acontece na listagem.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Optional

from bs4 import BeautifulSoup
from unidecode import unidecode

from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession

logger = logging.getLogger("zleilao.scraper.generic")

# Orgaos que identificam pregao judicial pelo titulo (mesma lista que os
# parsers dedicados usam quando a fonte nao separa judicial de extrajudicial).
JUDICIAL_RE = re.compile(
    r"\b(JUDICIAL|VARA|JUIZADO|TRIBUNAL|JU[IÍ]ZO|COMARCA|F[OÓ]RUM|JUSTI[CÇ]A|TJ[A-Z]{0,4}|TRT|TRF"
    r"|MASSA FALIDA|FAL[EÊ]NCIA|HASTAS?)\b",
    re.I,
)
EXTRAJUDICIAL_RE = re.compile(r"EXTRA\s*-?\s*JUDICIAL", re.I)

# "21/10 16:00", "30/10 16:01", "21/10" — dia/mes sem ano. O `(?!/\d)` evita
# engolir o inicio de uma data completa, que `parse_datetime_br` ja' trata.
DATE_NO_YEAR_RE = re.compile(r"\b(\d{2})/(\d{2})(?!/\d)(?:\D{1,6}?(\d{1,2})[:h](\d{2}))?")

STATUS_VALUES = {"open", "soon", "closed", "sold", "withdrawn"}


def parse_datetime_sem_ano(text: str | None, today: date | None = None) -> Optional[datetime]:
    """'21/10 16:00' -> 21/10 do ano corrente; se ja' passou ha' mais de 30
    dias, do ano seguinte (a capa de um leiloeiro so' lista pregoes futuros;
    30 dias de folga cobrem o pregao que encerrou ha' pouco e ainda esta' no
    ar). Devolve None sem dia/mes reconhecivel."""
    if not text:
        return None
    today = today or date.today()
    m = DATE_NO_YEAR_RE.search(text)
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    hh, mm = int(m.group(3) or 0), int(m.group(4) or 0)
    try:
        dt = datetime(today.year, mo, d, hh, mm)
    except ValueError:
        return None
    if (today - dt.date()).days > 30:
        try:
            dt = dt.replace(year=today.year + 1)
        except ValueError:  # 29/02 num ano que nao e' bissexto
            return None
    return dt


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
        # Campos lidos da pagina do pregao (modo duas etapas), nao do card:
        # {"date": {"selector": ".header .start"}, "end_date": {...}, "modality": {...}}
        "page_fields": {},
        "detail": {},
        "category_hint": "veiculos",
        # "judicial" | "extrajudicial" | "auto" (pelo titulo do pregao)
        "auction_type": "extrajudicial",
        "auction_type_default": "extrajudicial",
        # UF assumida quando a fonte da' a cidade sem UF; vazio = nao assume
        "default_state": "",
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
        if val and spec.get("sub"):
            pattern, repl = spec["sub"]
            val = re.sub(pattern, repl, val)
        if val and spec.get("map"):
            val = self._map_value(val, spec["map"])
        return val or None

    @staticmethod
    def _map_value(val: str, mapping: dict) -> str:
        """Compara sem acento nem caixa: o admin escreve "em leilao" e a fonte
        manda "EM LEILÃO". Sem correspondencia, o texto segue como veio."""
        key = unidecode(val).strip().lower()
        for k, v in mapping.items():
            if unidecode(str(k)).strip().lower() == key:
                return str(v)
        return val

    def _today(self) -> date:
        """Separado para os testes fixarem a data (datas sem ano dependem dela)."""
        return date.today()

    def parse_date(self, text: str | None) -> Optional[datetime]:
        """Data completa primeiro; sem ano, assume o corrente/proximo."""
        return self.parse_datetime_br(text) or parse_datetime_sem_ano(text, self._today())

    def resolve_auction_type(self, *texts: Optional[str]) -> Optional[str]:
        cfg = self.cfg("auction_type", "extrajudicial")
        if cfg != "auto":
            return cfg
        t = " ".join(x for x in texts if x)
        if EXTRAJUDICIAL_RE.search(t):
            return "extrajudicial"
        if JUDICIAL_RE.search(t):
            return "judicial"
        return self.cfg("auction_type_default", "extrajudicial")

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
                "end_date": self._extract(el, cfg.get("end_date")),
                "modality": self._extract(el, cfg.get("modality")),
                "location": self._extract(el, cfg.get("location")),
            })
        return out

    PAGE_FIELD_KEYS = ("title", "date", "end_date", "modality", "location")

    def parse_page_fields(self, soup: BeautifulSoup) -> dict:
        """Campos do cabecalho da pagina do pregao. So' entram os que tiverem
        valor, para nao apagar o que a lista de pregoes trouxe."""
        specs = self.cfg("page_fields") or {}
        out: dict = {}
        for key in self.PAGE_FIELD_KEYS:
            if specs.get(key):
                val = self._extract(soup, specs[key])
                if val:
                    out[key] = val
        return out

    def parse_listing(self, html: str, auction: dict | None = None) -> list[ScrapedItem]:
        soup = BeautifulSoup(html, "lxml")
        if auction is not None and self.cfg("page_fields"):
            # o cabecalho da pagina sobrepoe a capa, que costuma vir resumida
            auction = {**auction, **self.parse_page_fields(soup)}
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
        auction = auction or {}

        loc = self.reject_unknown(self._extract(el, fields.get("location")) or auction.get("location"))
        city, state = self.parse_city_state(loc)
        city, state = self.reject_unknown(city), self.reject_unknown(state)
        if city and not state and self.cfg("default_state"):
            state = str(self.cfg("default_state")).strip().upper()[:2]
        image = self._extract(el, fields.get("image"))
        starts_at = self.parse_date(self._extract(el, fields.get("date")) or auction.get("date"))
        ends_at = self.parse_date(self._extract(el, fields.get("end_date")) or auction.get("end_date"))
        sessions = [ScrapedSession(kind="unica", starts_at=starts_at, ends_at=ends_at)] if starts_at or ends_at else []
        auction_type = self.resolve_auction_type(auction.get("title"), self._extract(el, fields.get("auction_type")))

        if auction:
            scraped_auction = ScrapedAuction(
                external_id=auction["external_id"],
                title=auction.get("title"),
                auction_type=auction_type,
                modality=(auction.get("modality") or "").lower() or None,
                official_url=auction["url"],
                sessions=sessions,
            )
        else:
            scraped_auction = ScrapedAuction(
                external_id=self._extract(el, fields.get("auction_id")) or f"lot-{ext}",
                auction_type=auction_type,
                official_url=url,
                sessions=sessions,
            )

        status_txt = self._extract(el, fields.get("status"))
        status = status_txt if status_txt in STATUS_VALUES else self.status_from_text(status_txt)

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
            category_hint=self._extract(el, fields.get("category")) or self.cfg("category_hint", "veiculos"),
            status_hint=status,
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
                if item.city and not item.state and self.cfg("default_state"):
                    item.state = str(self.cfg("default_state")).strip().upper()[:2]
        if detail.get("images_regex"):
            # a fonte costuma referenciar as fotos por caminho relativo
            imgs = [self.abs_url(u) for u in dict.fromkeys(re.findall(detail["images_regex"], html))]
            imgs = [u for u in imgs if self.reject_placeholder(u)]
            if imgs:
                item.images = imgs[:12]
                item.image_url = item.image_url or imgs[0]
