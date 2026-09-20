"""Filtro de busca compartilhado entre a vitrine e o motor de alertas.

O filtro salvo guarda exatamente as chaves da busca publica, e o matcher roda
a MESMA query. Se o filtro e o alerta usassem codigos diferentes, o usuario
receberia alerta de lote que a busca nao mostra — ou pior, deixaria de receber
o que ele viu ao salvar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.lifecycle import VISIBLE_STATUSES
from app.models import Auction, Category, Item, Source

#: Chaves aceitas em `saved_filters.criteria` e na query string da vitrine.
CRITERIA_KEYS = (
    "q", "category", "brand", "model", "year_min", "year_max", "price_min", "price_max",
    "state", "city", "source", "condition", "auction_type",
)

_INT_KEYS = {"year_min", "year_max"}
_FLOAT_KEYS = {"price_min", "price_max"}


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
    }
    parts = [f"{labels.get(k, k)}: {v}" for k, v in criteria.items() if v not in (None, "")]
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
    return stmt
