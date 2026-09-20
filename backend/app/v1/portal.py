"""Rotas publicas da vitrine (sem autenticacao)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.timeutil import now_brt
from app.engine.geo import search_cities
from app.engine.lifecycle import VISIBLE_STATUSES
from app.engine.search import apply_filters, base_query, haversine_sql, normalize_criteria, radius_center
from app.models import Auction, BrandingAsset, Category, ClickEvent, Item, ItemOpportunity, Source
from app.schemas import AuctionOut, CategoryTreeOut, FacetValue, ItemDetailOut, ItemPage, PageMeta
from app.settings_service import get_setting, get_setting_int
from app.v1.serializers import SerializerContext

router = APIRouter()

SORTS = {"relevance", "price_asc", "price_desc", "session_asc", "newest", "distance", "opportunity"}


# ── branding / stats ───────────────────────────────────────────────

@router.get("/portal/branding")
async def branding(db: AsyncSession = Depends(get_db)):
    assets = {a.key: a for a in (await db.execute(select(BrandingAsset))).scalars().all()}

    def url_for(key: str) -> str | None:
        a = assets.get(key)
        return f"/api/branding/{key}?v={int(a.updated_at.timestamp())}" if a else None

    return {
        "logo_dark": url_for("logo_dark"), "logo_light": url_for("logo_light"), "favicon": url_for("favicon"),
        "site_title": await get_setting(db, "brand_site_title", "ZConnect Leilão"),
        "tagline": await get_setting(db, "brand_tagline", ""),
        "disclaimer": await get_setting(db, "portal_disclaimer", ""),
    }


@router.get("/portal/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    now = now_brt()
    published = await db.scalar(select(func.count(Item.id)).where(Item.status.in_(VISIBLE_STATUSES))) or 0
    sources_active = await db.scalar(select(func.count(Source.id)).where(Source.is_active.is_(True))) or 0
    upcoming = await db.scalar(select(func.count(Auction.id)).where(Auction.starts_at >= now, Auction.starts_at <= now + timedelta(days=7))) or 0
    next_at = await db.scalar(select(func.min(Item.next_session_at)).where(Item.status.in_(VISIBLE_STATUSES), Item.next_session_at >= now))
    last_collected = await db.scalar(select(func.max(Source.last_run_at)))
    by_cat = (await db.execute(
        select(Category.slug, Category.name, func.count(Item.id))
        .join(Item, Item.category_id == Category.id).where(Item.status.in_(VISIBLE_STATUSES)).group_by(Category.slug, Category.name)
    )).all()
    return {
        "items_published": published, "sources_active": sources_active, "auctions_upcoming_7d": upcoming,
        "next_session_at": next_at, "last_collected_at": last_collected,
        "by_category": [{"slug": s, "name": n, "count": c} for s, n, c in by_cat],
    }


# ── categorias ─────────────────────────────────────────────────────

@router.get("/portal/categories", response_model=list[CategoryTreeOut])
async def categories(db: AsyncSession = Depends(get_db)):
    cats = (await db.execute(select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.id))).scalars().all()
    counts = dict((await db.execute(
        select(Item.category_id, func.count(Item.id)).where(Item.status.in_(VISIBLE_STATUSES)).group_by(Item.category_id)
    )).all())
    ctx = SerializerContext(db)
    ctx.categories = {c.id: c for c in cats}
    nodes: dict[int, CategoryTreeOut] = {}
    for c in cats:
        await ctx.fields_for(c.id)
        nodes[c.id] = CategoryTreeOut(
            id=c.id, name=c.name, slug=c.slug, parent_id=c.parent_id, is_active=c.is_active, sort_order=c.sort_order,
            keywords=c.keywords or [], llm_hint=c.llm_hint, path=c.path, created_at=c.created_at,
            items_count=counts.get(c.id, 0), fields=ctx.field_defs_out(c.id), children=[],
        )
    roots: list[CategoryTreeOut] = []
    for c in cats:
        node = nodes[c.id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id].children.append(node)
            nodes[c.parent_id].items_count += node.items_count
        else:
            roots.append(node)
    return roots


# ── busca ──────────────────────────────────────────────────────────

# O filtro e a query base moram em `engine/search.py`, compartilhados com o
# motor de alertas: o filtro salvo precisa casar exatamente com o que a busca
# mostra, e duas implementações divergiriam na primeira mudança.


@router.get("/portal/items", response_model=ItemPage)
async def search_items(
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    category: Optional[str] = Query(None, description="slug da categoria (inclui subcategorias)"),
    brand: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = Query(None, description="slug da fonte"),
    condition: Optional[str] = None,
    auction_type: Optional[str] = None,
    session_from: Optional[datetime] = None,
    session_to: Optional[datetime] = None,
    near_city: Optional[str] = Query(None, description="cidade de referencia para busca por raio"),
    near_state: Optional[str] = Query(None, description="UF da cidade de referencia"),
    radius_km: Optional[float] = Query(None, ge=1, le=3000),
    status: Optional[str] = None,
    sort: str = "relevance",
    page: int = Query(1, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    facets: bool = True,
):
    page_size = page_size or await get_setting_int(db, "portal_items_per_page", 24)
    category_path = None
    if category:
        cat = await db.scalar(select(Category).where(Category.slug == category))
        if not cat:
            raise HTTPException(404, "Categoria não encontrada")
        category_path = cat.path

    criteria = normalize_criteria({
        "q": q, "category": category, "brand": brand, "model": model,
        "year_min": year_min, "year_max": year_max, "price_min": price_min, "price_max": price_max,
        "state": state, "city": city, "source": source, "condition": condition,
        "auction_type": auction_type, "near_city": near_city, "near_state": near_state,
        "radius_km": radius_km,
    })
    extras = dict(category_path=category_path, status=status,
                  session_from=session_from, session_to=session_to)

    stmt = apply_filters(base_query(), criteria, **extras)
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    if sort not in SORTS:
        sort = "relevance"
    if sort == "price_asc":
        stmt = stmt.order_by(Item.price.asc().nulls_last(), Item.id.desc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Item.price.desc().nulls_last(), Item.id.desc())
    elif sort == "newest":
        stmt = stmt.order_by(Item.first_seen_at.desc(), Item.id.desc())
    elif sort == "distance" and (center := radius_center(criteria)):
        # Ordenação natural da busca por raio: do mais perto para o mais longe.
        (clat, clng), _ = center
        stmt = stmt.order_by(haversine_sql(clat, clng).asc(), Item.price.asc().nulls_last())
    elif sort == "opportunity":
        # RN-010: maior desconto primeiro. Lote sem score fica no fim — ausência
        # de referência não é desconto zero, é "não sabemos".
        stmt = stmt.outerjoin(ItemOpportunity, ItemOpportunity.item_id == Item.id).order_by(
            ItemOpportunity.score.desc().nulls_last(), Item.next_session_at.asc().nulls_last())
    elif sort == "session_asc" or not q:
        stmt = stmt.order_by(Item.next_session_at.asc().nulls_last(), Item.first_seen_at.desc())
    else:
        stmt = stmt.order_by(func.ts_rank(Item.search_tsv, func.plainto_tsquery("portuguese", q)).desc(), Item.next_session_at.asc().nulls_last())

    stmt = stmt.options(selectinload(Item.auction)).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().unique().all()
    ctx = await SerializerContext(db).load(items)

    facet_out: dict[str, list[FacetValue]] = {}
    if facets:
        base = apply_filters(base_query(), criteria, **extras).order_by(None)

        async def facet(col, label_col=None, limit=30):
            sub = base.with_only_columns(col.label("v"), (label_col if label_col is not None else col).label("l")).subquery()
            rows = (await db.execute(
                select(sub.c.v, sub.c.l, func.count()).where(sub.c.v.isnot(None)).group_by(sub.c.v, sub.c.l).order_by(func.count().desc()).limit(limit)
            )).all()
            return [FacetValue(value=str(v), label=str(l) if l is not None else None, count=c) for v, l, c in rows]

        facet_out["states"] = await facet(Item.state)
        facet_out["sources"] = await facet(Source.slug, Source.name)
        facet_out["categories"] = await facet(Category.slug, Category.name)
        facet_out["brands"] = await facet(Item.brand)
        facet_out["conditions"] = await facet(Item.condition)
        facet_out["auction_types"] = await facet(Auction.auction_type)

    return ItemPage(
        items=[ctx.card(i) for i in items],
        meta=PageMeta(page=page, page_size=page_size, total=total, pages=max(1, math.ceil(total / page_size))),
        facets=facet_out,
    )


@router.get("/portal/cities")
async def cities(q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=20)):
    """Autocomplete de município para a busca por raio. Resolve na base local
    de 5.571 municípios — sem chamada externa."""
    return search_cities(q, limit)


@router.get("/portal/brands", response_model=list[FacetValue])
async def brands(category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Item.brand, func.count()).where(Item.status.in_(VISIBLE_STATUSES), Item.brand.isnot(None))
    if category:
        stmt = stmt.join(Category, Category.id == Item.category_id).where(Category.path.like(f"%{category}%"))
    rows = (await db.execute(stmt.group_by(Item.brand).order_by(func.count().desc()))).all()
    return [FacetValue(value=b, count=c) for b, c in rows]


@router.get("/portal/models", response_model=list[FacetValue])
async def models(brand: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Item.model, func.count()).where(Item.status.in_(VISIBLE_STATUSES), func.lower(Item.brand) == brand.lower(), Item.model.isnot(None))
        .group_by(Item.model).order_by(func.count().desc()).limit(100)
    )).all()
    return [FacetValue(value=m, count=c) for m, c in rows]


# ── detalhe / pregao / clique ──────────────────────────────────────

@router.get("/portal/items/{item_id}", response_model=ItemDetailOut)
async def item_detail(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(
        select(Item).where(Item.id == item_id)
        .options(selectinload(Item.auction).selectinload(Auction.sessions), selectinload(Item.price_history))
    )
    if not item or item.status not in VISIBLE_STATUSES + ("closed",):
        raise HTTPException(404, "Lote não encontrado ou fora da vitrine")
    ctx = await SerializerContext(db).load([item])
    return await ctx.detail(item, await get_setting(db, "portal_disclaimer", ""))


@router.get("/portal/items/{item_id}/go")
async def go_to_source(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Lote não encontrado")
    db.add(ClickEvent(item_id=item.id, source_id=item.source_id, referer=(request.headers.get("referer") or "")[:500]))
    await db.commit()
    return RedirectResponse(item.official_url, status_code=302)


@router.get("/portal/auctions/upcoming", response_model=list[AuctionOut])
async def upcoming_auctions(days: int = Query(7, ge=1, le=60), limit: int = Query(10, ge=1, le=50), db: AsyncSession = Depends(get_db)):
    now = now_brt()
    rows = (await db.execute(
        select(Auction, func.count(Item.id)).join(Item, Item.auction_id == Auction.id)
        .where(Item.status.in_(VISIBLE_STATUSES), Auction.starts_at.isnot(None), Auction.ends_at >= now, Auction.starts_at <= now + timedelta(days=days))
        .group_by(Auction.id).order_by(Auction.starts_at.asc()).limit(limit)
        .options(selectinload(Auction.sessions))
    )).all()
    ctx = SerializerContext(db)
    await ctx.load([])
    return [await ctx.auction(a, c) for a, c in rows]


@router.get("/portal/auctions/{auction_id}")
async def auction_detail(auction_id: int, db: AsyncSession = Depends(get_db)):
    auction = await db.scalar(select(Auction).where(Auction.id == auction_id).options(selectinload(Auction.sessions)))
    if not auction:
        raise HTTPException(404, "Pregão não encontrado")
    items = (await db.execute(
        select(Item).where(Item.auction_id == auction.id, Item.status.in_(VISIBLE_STATUSES + ("closed",)))
        .order_by(Item.lot_number.asc().nulls_last(), Item.id).options(selectinload(Item.auction))
    )).scalars().all()
    ctx = await SerializerContext(db).load(items)
    return {"auction": await ctx.auction(auction, len(items)), "items": [ctx.card(i) for i in items]}
