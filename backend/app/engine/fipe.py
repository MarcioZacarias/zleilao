"""Referência de preço de mercado pela tabela FIPE.

**Por que FIPE e não mediana de anúncios.** A EF previa calcular o preço de
referência a partir de anúncios de marketplaces. Ao avaliar as fontes, três
delas restringem coleta automatizada no robots.txt (o Webmotors proíbe
`/comprar/`, o Mercado Livre nega `Disallow: /` a agentes de IA). A tabela
FIPE é pública, feita para consulta, atualizada mensalmente e é *a* referência
que o mercado brasileiro usa — inclusive os próprios leiloeiros. Usá-la como
referência primária entrega o comparador sem depender de scraping de terceiros;
anúncios de marketplace ficam como complemento opcional por fonte (RN-009).

O casamento entre o lote e o código FIPE é por marca + similaridade de modelo +
ano, e é **conservador**: sem confiança suficiente, não devolve referência —
melhor não ter score do que ter um score errado (mesmo espírito da RN-010).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Optional

import httpx
from unidecode import unidecode

logger = logging.getLogger("zleilao.fipe")

DEFAULT_BASE = "https://parallelum.com.br/fipe/api/v1"
#: tipos aceitos pela API e a categoria do nosso catálogo que cada um cobre
VEHICLE_TYPES = {"carros": ("carros", "utilitarios"), "motos": ("motos",), "caminhoes": ("caminhoes",)}
#: similaridade mínima de modelo para aceitar o casamento
MIN_MODEL_RATIO = 0.66


class FipeUnavailable(Exception):
    """API fora do ar ou limitando: o ciclo para e tenta depois."""


@dataclass
class FipeMatch:
    value: Decimal
    fipe_code: str
    model_label: str
    year: int
    fuel: str | None
    reference_month: str
    ratio: float


def norm(text: str | None) -> str:
    """Normaliza para comparação: sem acento, minúsculo, só alfanumérico."""
    return re.sub(r"[^a-z0-9 ]+", " ", unidecode(text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    return [t for t in norm(text).split() if t]


def model_similarity(item_model: str, fipe_model: str) -> float:
    """Quanto o modelo do lote se parece com o da FIPE.

    O que separa modelos de carro é a **primeira palavra**: "Gol" e "Golf" são
    veículos diferentes, enquanto "Sandero GTL" e "Sandero GT Line" são o mesmo.
    Por isso o primeiro token é eliminatório e vale a maior parte da nota; os
    tokens seguintes (a versão) apenas refinam a escolha entre variantes do
    mesmo modelo, porque a fonte abrevia a versão de forma imprevisível.
    """
    a, b = _tokens(item_model), _tokens(fipe_model)
    if not a or not b:
        return 0.0
    if a[0] != b[0]:
        # tolera plural/sufixo curto ("classe a" x "classe"), não troca de modelo
        if not (a[0].startswith(b[0]) or b[0].startswith(a[0])) or min(len(a[0]), len(b[0])) < 4:
            return 0.0
    rest = a[1:]
    if not rest:
        coverage = 1.0
    else:
        hits = sum(1 for t in rest if any(t == x or (len(t) > 2 and t in x) or (len(x) > 2 and x in t) for x in b[1:]))
        coverage = hits / len(rest)
    seq = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return round(0.60 + 0.25 * coverage + 0.15 * seq, 3)


def parse_brl(value: str | None) -> Optional[Decimal]:
    if not value:
        return None
    digits = re.sub(r"[^\d,]", "", value).replace(",", ".")
    try:
        return Decimal(digits).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        return None


class FipeClient:
    """Cliente com cache em memória. A tabela muda uma vez por mês, então
    marcas e modelos são consultados uma vez por processo."""

    def __init__(self, base_url: str = DEFAULT_BASE, timeout: float = 25.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._brands: dict[str, list[dict]] = {}
        self._models: dict[tuple[str, str], list[dict]] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout, headers={"Accept": "application/json"})
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str) -> Any:
        assert self._client is not None, "use 'async with FipeClient()'"
        try:
            resp = await self._client.get(f"{self.base_url}{path}")
        except httpx.RequestError as exc:
            raise FipeUnavailable(f"{exc.__class__.__name__}: {exc}") from exc
        if resp.status_code == 429:
            raise FipeUnavailable("429 — limite de requisicoes da API FIPE")
        if resp.status_code >= 500:
            raise FipeUnavailable(f"API FIPE respondeu {resp.status_code}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def brands(self, vehicle: str) -> list[dict]:
        if vehicle not in self._brands:
            self._brands[vehicle] = await self._get(f"/{vehicle}/marcas") or []
        return self._brands[vehicle]

    async def models(self, vehicle: str, brand_code: str) -> list[dict]:
        key = (vehicle, brand_code)
        if key not in self._models:
            data = await self._get(f"/{vehicle}/marcas/{brand_code}/modelos") or {}
            self._models[key] = data.get("modelos", []) if isinstance(data, dict) else []
        return self._models[key]

    async def years(self, vehicle: str, brand_code: str, model_code: str) -> list[dict]:
        return await self._get(f"/{vehicle}/marcas/{brand_code}/modelos/{model_code}/anos") or []

    async def price(self, vehicle: str, brand_code: str, model_code: str, year_code: str) -> dict | None:
        data = await self._get(f"/{vehicle}/marcas/{brand_code}/modelos/{model_code}/anos/{year_code}")
        if isinstance(data, dict) and data.get("Valor"):
            return data
        return None

    async def find_brand(self, vehicle: str, brand: str) -> Optional[dict]:
        target = norm(brand)
        if not target:
            return None
        options = await self.brands(vehicle)
        exact = [b for b in options if norm(b["nome"]) == target]
        if exact:
            return exact[0]
        # "VW" -> "VW - VolksWagen"; "Mercedes-Benz" -> "Mercedes-Benz"
        partial = [b for b in options if target in norm(b["nome"]) or norm(b["nome"]).startswith(target)]
        return partial[0] if partial else None

    async def lookup(self, *, vehicle: str, brand: str, model: str, year: int,
                     fuel_hint: str | None = None) -> Optional[FipeMatch]:
        """Melhor casamento para (marca, modelo, ano). None se não houver
        confiança suficiente."""
        b = await self.find_brand(vehicle, brand)
        if not b:
            return None
        models = await self.models(vehicle, str(b["codigo"]))
        scored = [(model_similarity(model, m["nome"]), m) for m in models]
        scored = [(r, m) for r, m in scored if r >= MIN_MODEL_RATIO]
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])

        # Entre os modelos parecidos, vale o primeiro que tem o ano pedido.
        for ratio, m in scored[:6]:
            years = await self.years(vehicle, str(b["codigo"]), str(m["codigo"]))
            candidates = [y for y in years if str(y.get("codigo", "")).split("-")[0] == str(year)]
            if not candidates:
                continue
            if fuel_hint:
                fh = norm(fuel_hint)
                preferred = [y for y in candidates if fh[:4] in norm(y.get("nome", ""))]
                candidates = preferred or candidates
            data = await self.price(vehicle, str(b["codigo"]), str(m["codigo"]), str(candidates[0]["codigo"]))
            if not data:
                continue
            value = parse_brl(data.get("Valor"))
            if value is None:
                continue
            return FipeMatch(
                value=value,
                fipe_code=str(data.get("CodigoFipe") or ""),
                model_label=str(data.get("Modelo") or m["nome"]),
                year=int(data.get("AnoModelo") or year),
                fuel=data.get("Combustivel"),
                reference_month=str(data.get("MesReferencia") or "").strip(),
                ratio=ratio,
            )
        return None


def vehicle_type_for(category_path: str | None) -> Optional[str]:
    """Categoria do nosso catálogo -> tipo de veículo da FIPE."""
    if not category_path:
        return None
    leaf = category_path.split("/")[-1]
    for vehicle, cats in VEHICLE_TYPES.items():
        if leaf in cats:
            return vehicle
    return None
