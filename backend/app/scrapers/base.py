"""Base dos scrapers de leilao (evolucao do BaseScraper do Promo).

Cada fonte tem um parser dedicado que devolve `ScrapedItem`s. O scraper NAO
grava no banco: quem persiste e' `scheduler/jobs.py`. Isso permite o
endpoint de teste (`POST /sources/{id}/test`) rodar o parser a seco.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from unidecode import unidecode

logger = logging.getLogger("zleilao.scraper")

MONTHS_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


@dataclass
class ScrapedSession:
    kind: str  # 1a_praca | 2a_praca | unica | repasse | condicional
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    min_bid: Optional[Decimal] = None


@dataclass
class ScrapedAuction:
    external_id: str
    title: Optional[str] = None
    auctioneer_name: Optional[str] = None
    auctioneer_registration: Optional[str] = None
    committer_name: Optional[str] = None
    modality: Optional[str] = None  # online | presencial | hibrido
    auction_type: Optional[str] = None  # judicial | extrajudicial
    official_url: Optional[str] = None
    sessions: list[ScrapedSession] = field(default_factory=list)


@dataclass
class ScrapedItem:
    external_id: str
    title: str
    official_url: str
    price: Optional[Decimal] = None
    price_kind: Optional[str] = "lance_inicial"
    price_second: Optional[Decimal] = None
    lot_number: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    location_text: Optional[str] = None
    image_url: Optional[str] = None
    images: list[str] = field(default_factory=list)
    description: Optional[str] = None
    # Campos que a fonte ja' entrega estruturados (marca, ano, km, laudo...)
    raw_attributes: dict[str, Any] = field(default_factory=dict)
    # Dica de categoria: slug ("carros", "motos") ou texto livre da fonte
    category_hint: Optional[str] = None
    status_hint: Optional[str] = None  # open | soon | closed | sold | withdrawn
    auction: Optional[ScrapedAuction] = None
    # Texto bruto (HTML do card/detalhe ou JSON) para `raw_items`
    raw_payload: Optional[str] = None


@dataclass
class ScrapeStats:
    pages: int = 0
    details: int = 0
    errors: int = 0
    notes: list[str] = field(default_factory=list)
    #: A varredura chegou ao fim do catalogo da fonte? `False` quando parou por
    #: limite de paginas, de leiloes ou por erro. So' uma varredura completa
    #: autoriza concluir que um item sumiu (RN-005): numa coleta parcial, o item
    #: pode apenas estar fora da janela vista.
    complete: bool = True

    def mark_partial(self, reason: str) -> None:
        if self.complete:
            self.complete = False
        if reason not in self.notes:
            self.notes.append(reason)


class BaseScraper(ABC):
    """Cliente httpx com atraso aleatorio, retry exponencial e helpers."""

    #: nome legivel do parser (aparece no admin)
    display_name: str = "Base"
    #: config default sugerida no cadastro da fonte
    default_config: dict[str, Any] = {}

    def __init__(self, source_id: int, base_url: str | None, config: dict | None, runtime: dict | None = None):
        self.source_id = source_id
        self.config = config or {}
        self.runtime = runtime or {}
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.client: httpx.AsyncClient | None = None
        self.stats = ScrapeStats()

    # ── configuracao ─────────────────────────────────────────────────

    @property
    @abstractmethod
    def default_base_url(self) -> str: ...

    def cfg(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def rt(self, key: str, default: Any = None) -> Any:
        return self.runtime.get(key, default)

    @property
    def fetch_details(self) -> bool:
        v = self.cfg("fetch_details", self.rt("fetch_details_default", True))
        return str(v).lower() in ("1", "true", "yes")

    @property
    def max_details(self) -> int:
        try:
            return int(self.cfg("max_details_per_run", self.rt("max_details_per_run", 60)))
        except (TypeError, ValueError):
            return 60

    def headers(self) -> dict[str, str]:
        if self.config.get("headers"):
            return dict(self.config["headers"])
        ua = self.rt("user_agent") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        h = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        # Client hints coerentes com a versao do User-Agent: o bot manager do
        # Sodre Santoro (Azion) devolvia 403 so' por eles faltarem, e nenhuma
        # das outras fontes se importa com a presenca deles.
        m = re.search(r"Chrome/(\d+)", ua)
        if m:
            v = m.group(1)
            h["sec-ch-ua"] = f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not-A.Brand";v="99"'
            h["sec-ch-ua-mobile"] = "?0"
            h["sec-ch-ua-platform"] = '"Windows"'
        return h

    #: Cabecalhos de uma chamada feita por script (fetch/XHR), nao de navegacao.
    XHR = {"Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}

    # ── ciclo de vida do client ──────────────────────────────────────

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(40.0),
            headers=self.headers(),
            follow_redirects=True,
            verify=str(self.cfg("verify_ssl", True)).lower() not in ("0", "false", "no"),
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def delay(self):
        lo = float(self.rt("request_delay_min", 1.0))
        hi = float(self.rt("request_delay_max", 3.0))
        if hi < lo:
            hi = lo
        await asyncio.sleep(random.uniform(lo, hi))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def fetch(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        assert self.client is not None, "use 'async with scraper:'"
        resp = await self.client.get(url, params=params, headers=headers)
        if resp.status_code in (403, 429, 503):
            raise httpx.HTTPStatusError(f"{resp.status_code} em {url}", request=resp.request, response=resp)
        resp.raise_for_status()
        return self._decode(resp)

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """Charset do header; senao utf-8 estrito; senao cp1252 (sites .NET antigos)."""
        if resp.charset_encoding:
            return resp.text
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return resp.content.decode("cp1252", errors="replace")

    async def fetch_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
        assert self.client is not None
        h = {"Accept": "application/json, text/plain, */*", **self.XHR}
        if headers:
            h.update(headers)
        resp = await self.client.get(url, params=params, headers=h)
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def post(
        self, url: str, *, data: dict | None = None, json: Any = None,
        params: dict | None = None, headers: dict | None = None,
    ) -> httpx.Response:
        """POST com o mesmo retry e os mesmos status tratados do `fetch`.
        `data` vai como formulario, `json` como corpo JSON. Fontes AJAX
        (Palacio, Sodre) e APIs de busca (Elasticsearch por tras do site)
        precisam disso; devolve a resposta inteira porque cada uma le de um
        jeito (HTML, JSON, "0" como erro)."""
        assert self.client is not None, "use 'async with scraper:'"
        h = dict(self.XHR)
        if headers:
            h.update(headers)
        resp = await self.client.post(url, data=data, json=json, params=params, headers=h)
        if resp.status_code in (403, 429, 503):
            raise httpx.HTTPStatusError(f"{resp.status_code} em {url}", request=resp.request, response=resp)
        resp.raise_for_status()
        return resp

    async def post_json(
        self, url: str, *, data: dict | None = None, json: Any = None,
        params: dict | None = None, headers: dict | None = None,
    ) -> Any:
        h = {"Accept": "application/json, text/plain, */*"}
        if headers:
            h.update(headers)
        return (await self.post(url, data=data, json=json, params=params, headers=h)).json()

    # ── contrato ─────────────────────────────────────────────────────

    @abstractmethod
    async def scrape(self) -> list[ScrapedItem]: ...

    async def run(self) -> list[ScrapedItem]:
        items = await self.scrape()
        seen: set[str] = set()
        unique: list[ScrapedItem] = []
        for it in items:
            if it.external_id in seen:
                continue
            seen.add(it.external_id)
            unique.append(it)
        logger.info("[%s] %d itens unicos (%d paginas, %d detalhes, %d erros)",
                    self.display_name, len(unique), self.stats.pages, self.stats.details, self.stats.errors)
        return unique

    # ── helpers ──────────────────────────────────────────────────────

    def abs_url(self, href: str) -> str:
        return urljoin(self.base_url + "/", href)

    @staticmethod
    def strip_tracking(url: str) -> str:
        parts = urlsplit(url)
        qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs), ""))

    @staticmethod
    def clean_text(text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def parse_brl(text: str | None) -> Optional[Decimal]:
        """'R$ 21.900,00' -> Decimal('21900.00'). Aceita numero puro."""
        if text is None:
            return None
        if isinstance(text, (int, float, Decimal)):
            try:
                return Decimal(str(text)).quantize(Decimal("0.01"))
            except InvalidOperation:
                return None
        m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", text.replace("\xa0", " "))
        if not m:
            return None
        inteiro = m.group(1).replace(".", "")
        cents = (m.group(2) or "0").ljust(2, "0")
        try:
            return Decimal(f"{inteiro}.{cents}")
        except InvalidOperation:
            return None

    @staticmethod
    def parse_datetime_br(text: str | None) -> Optional[datetime]:
        """'21/09/2026 às 10:00', '21/09/2026 10:00', '21/09/2026', ISO 8601."""
        if not text:
            return None
        t = text.strip()
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\D+(\d{1,2})[:h](\d{2}))?", t)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh = int(m.group(4)) if m.group(4) else 0
            mm = int(m.group(5)) if m.group(5) else 0
            try:
                return datetime(y, mo, d, hh, mm)
            except ValueError:
                return None
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", t)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
            except ValueError:
                return None
        return None

    @staticmethod
    def parse_city_state(text: str | None) -> tuple[Optional[str], Optional[str]]:
        """'Guaratinguetá, SP' | 'SANTO ANDRE/SP' | 'GOIÂNIA - GO' -> (cidade, UF)."""
        if not text:
            return None, None
        t = re.sub(r"\s+", " ", text).strip()
        m = re.search(r"([A-Za-zÀ-ÿ'\. ]+?)\s*[,/\-–]\s*([A-Z]{2})\b\s*$", t)
        if m:
            return m.group(1).strip().title(), m.group(2).upper()
        m = re.search(r"\b([A-Z]{2})\s*$", t)
        if m and len(t) > 3:
            return t[: m.start()].strip(" ,-/").title() or None, m.group(1)
        return t.title() or None, None

    # Valores que as fontes usam para dizer "nao sei" e que NAO podem virar
    # dado (RN-002: ausente fica "nao informado", nunca inventado nem exibido
    # como se fosse a cidade do lote).
    UNKNOWN_VALUES = {
        "si", "s/i", "sem informacao", "sem informacoes", "nao informado", "nao informada",
        "n/i", "ni", "-", "--", "nd", "n/d", "indefinido", "outros", "outro",
        "nao informando", "nao informou", "a informar", "a definir", "diversos", "varios",
    }

    @classmethod
    def reject_unknown(cls, value: str | None) -> Optional[str]:
        """Devolve None quando o texto e' um marcador de 'sem informacao'."""
        if not value:
            return None
        norm = unidecode(str(value)).strip().lower().rstrip(".")
        return None if norm in cls.UNKNOWN_VALUES else value

    @staticmethod
    def reject_placeholder(url: str | None) -> Optional[str]:
        """Descarta a imagem generica que a fonte serve quando o lote nao tem
        foto. Exibi-la seria mostrar a marca do leiloeiro no lugar do veiculo."""
        if not url:
            return None
        u = url.lower()
        if any(k in u for k in ("no-image", "noimage", "sem-imagem", "sem_imagem",
                                "imagem-indisponivel", "indisponivel", "placeholder", "default-")):
            return None
        return url

    @staticmethod
    def status_from_text(text: str | None) -> Optional[str]:
        t = (text or "").lower()
        if not t:
            return None
        if any(k in t for k in ("aberto", "em andamento", "receb", "repasse", "lance")):
            return "open"
        if any(k in t for k in ("em breve", "aguardando", "agendado")):
            return "soon"
        if "nao arrematado" in t or "não arrematado" in t or "naoarrematado" in t:
            return "closed"
        if any(k in t for k in ("vendido", "arrematado")):
            return "sold"
        if any(k in t for k in ("encerrado", "fechado", "finalizado", "executado")):
            return "closed"
        if any(k in t for k in ("retirado", "cancelado", "suspenso")):
            return "withdrawn"
        return None
