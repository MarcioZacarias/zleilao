"""Filtro de busca compartilhado entre a vitrine e o motor de alertas.

O filtro salvo guarda exatamente as chaves da busca publica, e o matcher roda
a MESMA query. Se o filtro e o alerta usassem codigos diferentes, o usuario
receberia alerta de lote que a busca nao mostra — ou pior, deixaria de receber
o que ele viu ao salvar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Select, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.engine.geo import bounding_box, coords_for
from app.engine.lifecycle import VISIBLE_STATUSES
from app.models import Auction, Category, Item, ItemDuplicate, Source

#: Chaves aceitas em `saved_filters.criteria` e na query string da vitrine.
CRITERIA_KEYS = (
    "q", "category", "brand", "model", "year_min", "year_max", "price_min", "price_max",
    "state", "city", "source", "condition", "auction_type",
    # busca por raio: cidade de referência + distância
    "near_city", "near_state", "radius_km",
)

_INT_KEYS = {"year_min", "year_max"}
_FLOAT_KEYS = {"price_min", "price_max", "radius_km"}


def normalize_criteria(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Descarta chaves desconhecidas e coage tipos. Um critério vazio é válido:
    significa "qualquer lote novo"."""
    out: dict[str, Any] = {}
    for key in CRITERIA_KEYS:
        val = (raw or {}).get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        if key in _INT_KEYS:
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                continue
        elif key in _FLOAT_KEYS:
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                continue
        else:
            out[key] = str(val).strip()[:120]
    return out


def describe_criteria(criteria: dict[str, Any]) -> str:
    """Resumo legivel, usado no nome sugerido do filtro e no corpo do alerta."""
    labels = {
        "q": "busca", "category": "categoria", "brand": "marca", "model": "modelo",
        "year_min": "ano de", "year_max": "ano ate", "price_min": "preco de",
        "price_max": "preco ate", "state": "UF", "city": "cidade", "source": "fonte",
        "condition": "condicao", "auction_type": "tipo",
        "near_city": "perto de", "near_state": "UF de referencia", "radius_km": "raio (km)",
    }
    skip = set()
    if criteria.get("near_city"):
        # As tres chaves do raio sao um conceito so: um item, nao tres.
        skip = {"near_city", "near_state", "radius_km"}
    parts = [f"{labels.get(k, k)}: {v}" for k, v in criteria.items()
             if v not in (None, "") and k not in skip]
    if skip:
        uf = criteria.get("near_state")
        raio = criteria.get("radius_km") or 100
        parts.append(f"ate {raio:g} km de {criteria['near_city']}" + (f"/{uf}" if uf else ""))
    return ", ".join(parts) if parts else "todos os lotes"


def base_query() -> Select:
    return (
        select(Item)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(Category, Category.id == Item.category_id)
        .outerjoin(Auction, Auction.id == Item.auction_id)
    )


async def category_path_for(db: AsyncSession, slug: str | None) -> Optional[str]:
    if not slug:
        return None
    return await db.scalar(select(Category.path).where(Category.slug == slug))


def apply_filters(
    stmt: Select,
    criteria: dict[str, Any],
    *,
    category_path: str | None = None,
    status: str | None = None,
    session_from: datetime | None = None,
    session_to: datetime | None = None,
) -> Select:
    """Aplica o criterio. `category_path` vem resolvido por `category_path_for`
    porque a busca guarda o slug, mas o filtro precisa pegar a subarvore."""
    stmt = stmt.where(Item.status.in_(VISIBLE_STATUSES if status in (None, "", "all") else (status,)))

    if status in (None, "", "all"):
        # Espelho fundido (F4) some enquanto o canonico estiver visivel; se o
        # canonico encerra, o espelho volta a aparecer por conta propria.
        canon = aliased(Item)
        stmt = stmt.where(~exists().where(
            ItemDuplicate.duplicate_item_id == Item.id,
            ItemDuplicate.status == "confirmed",
            canon.id == ItemDuplicate.canonical_item_id,
            canon.status.in_(VISIBLE_STATUSES),
        ))

    if category_path:
        stmt = stmt.where(Category.path.like(f"{category_path}%"))

    q = criteria.get("q")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Item.search_tsv.op("@@")(func.plainto_tsquery("portuguese", q)),
            Item.title.ilike(like), Item.brand.ilike(like), Item.model.ilike(like),
        ))
    if criteria.get("brand"):
        stmt = stmt.where(func.lower(Item.brand) == str(criteria["brand"]).lower())
    if criteria.get("model"):
        stmt = stmt.where(Item.model.ilike(f"%{criteria['model']}%"))
    if criteria.get("year_min") is not None:
        stmt = stmt.where(Item.year_model >= criteria["year_min"])
    if criteria.get("year_max") is not None:
        stmt = stmt.where(Item.year_model <= criteria["year_max"])
    if criteria.get("price_min") is not None:
        stmt = stmt.where(Item.price >= criteria["price_min"])
    if criteria.get("price_max") is not None:
        stmt = stmt.where(Item.price <= criteria["price_max"])
    if criteria.get("state"):
        stmt = stmt.where(Item.state == str(criteria["state"]).upper())
    if criteria.get("city"):
        stmt = stmt.where(Item.city.ilike(f"%{criteria['city']}%"))
    if criteria.get("source"):
        stmt = stmt.where(Source.slug == criteria["source"])
    if criteria.get("condition"):
        stmt = stmt.where(Item.condition == criteria["condition"])
    if criteria.get("auction_type"):
        stmt = stmt.where(Auction.auction_type == criteria["auction_type"])
    if session_from:
        stmt = stmt.where(Item.next_session_at >= session_from)
    if session_to:
        stmt = stmt.where(Item.next_session_at <= session_to)

    # Busca por raio: o retângulo usa o índice (lat, lng) e a distância exata
    # (Haversine) filtra as pontas. Sem o retângulo, um raio de 100 km leria a
    # tabela inteira.
    center = radius_center(criteria)
    if center is None and wants_radius(criteria):
        # Pediu raio e a cidade nao foi reconhecida: nao casa nada. Ignorar o
        # filtro devolveria o pais inteiro para quem pediu 60 km.
        return stmt.where(false())
    if center:
        (lat, lng), radius = center
        lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius)
        stmt = stmt.where(
            Item.lat.isnot(None), Item.lng.isnot(None),
            Item.lat.between(lat_min, lat_max), Item.lng.between(lng_min, lng_max),
            haversine_sql(lat, lng) <= radius,
        )
    return stmt


def wants_radius(criteria: dict[str, Any]) -> bool:
    """O criterio pede busca por raio (tendo a cidade sido reconhecida ou nao)."""
    return bool(criteria.get("near_city")) and bool(criteria.get("radius_km"))


def radius_center(criteria: dict[str, Any]) -> tuple[tuple[float, float], float] | None:
    """(coordenada, raio) quando o critério pede busca por raio."""
    radius = criteria.get("radius_km")
    city, state = criteria.get("near_city"), criteria.get("near_state")
    if not radius or not city or not state:
        return None
    try:
        radius = float(radius)
    except (TypeError, ValueError):
        return None
    if radius <= 0 or radius > 3000:
        return None
    coords = coords_for(str(city), str(state))
    return (coords, radius) if coords else None


def haversine_sql(lat: float, lng: float):
    """Distância em km entre o item e o ponto, em SQL puro — sem PostGIS."""
    return 6371.0 * func.acos(
        func.least(
            1.0,
            func.cos(func.radians(lat)) * func.cos(func.radians(Item.lat))
            * func.cos(func.radians(Item.lng) - func.radians(lng))
            + func.sin(func.radians(lat)) * func.sin(func.radians(Item.lat)),
        )
    )
