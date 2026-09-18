"""Itens (admin): listagem com filtros operacionais, fila de revisao,
edicao manual, reextracao e publicacao forcada."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.timeutil import now_brt
from app.engine.category_fields import effective_fields, validate_attributes
from app.engine.normalizer import LLMUnavailable, normalize_item, refresh_search_vector
from app.models import Auction, Category, Item, Source
from app.schemas import ItemAdminOut, ItemAdminPage, ItemUpdate, PageMeta
from app.v1.serializers import SerializerContext

router = APIRouter()


@router.get("", response_model=ItemAdminPage)
async def list_items(
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    status: Optional[str] = None,
    extraction_status: Optional[str] = None,
    source_id: Optional[int] = None,
    category_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = "updated_desc",
):
    stmt = select(Item)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Item.title.ilike(like), Item.external_id.ilike(like), Item.brand.ilike(like), Item.model.ilike(like)))
    if status:
        stmt = stmt.where(Item.status.in_(status.split(",")))
    if extraction_status:
        stmt = stmt.where(Item.extraction_status.in_(extraction_status.split(",")))
    if source_id:
        stmt = stmt.where(Item.source_id == source_id)
    if category_id:
        stmt = stmt.where(Item.category_id == category_id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {
        "updated_desc": Item.updated_at.desc(), "first_seen_desc": Item.first_seen_at.desc(),
        "session_asc": Item.next_session_at.asc().nulls_last(), "price_desc": Item.price.desc().nulls_last(),
    }.get(sort, Item.updated_at.desc())
    rows = (await db.execute(stmt.order_by(order, Item.id.desc()).options(selectinload(Item.auction)).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    ctx = await SerializerContext(db).load(rows)
    return ItemAdminPage(items=[ctx.admin(i) for i in rows], meta=PageMeta(page=page, page_size=page_size, total=total, pages=max(1, math.ceil(total / page_size))))


@router.get("/summary")
async def items_summary(db: AsyncSession = Depends(get_db)):
    by_status = dict((await db.execute(select(Item.status, func.count()).group_by(Item.status))).all())
    by_extraction = dict((await db.execute(select(Item.extraction_status, func.count()).group_by(Item.extraction_status))).all())
    return {"by_status": by_status, "by_extraction": by_extraction}


@router.get("/{item_id}", response_model=ItemAdminOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.auction)))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    ctx = await SerializerContext(db).load([item])
    return ctx.admin(item)


@router.patch("/{item_id}", response_model=ItemAdminOut)
async def update_item(item_id: int, data: ItemUpdate, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.auction)))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    changes = data.model_dump(exclude_unset=True)
    attrs_in = changes.pop("attributes", None)
    for k, v in changes.items():
        setattr(item, k, v)
    if attrs_in is not None:
        category = await db.get(Category, item.category_id) if item.category_id else None
        fields = [f for f, _ in await effective_fields(db, category)] if category else []
        merged = {**{k: v for k, v in (item.attributes or {}).items() if not k.startswith("_")}, **attrs_in}
        clean, errors = validate_attributes(fields, merged) if fields else (merged, [])
        clean.update({k: v for k, v in (item.attributes or {}).items() if k.startswith("_")})
        item.attributes = clean
        item.brand = clean.get("marca") or item.brand
        item.model = clean.get("modelo") or item.model
        item.year_model = clean.get("ano_modelo") or item.year_model
        item.km = clean.get("km") if clean.get("km") is not None else item.km
        item.condition = clean.get("condicao") or item.condition
        if item.extraction_status in ("review", "failed"):
            item.extraction_status = "done"
            item.extraction_error = "; ".join(errors) if errors else None
            item.extraction_version = (item.extraction_version or "") + "+manual"
            if item.status == "review":
                item.status = "collected"
    await refresh_search_vector(db, item)
    await db.commit()
    await db.refresh(item)
    ctx = await SerializerContext(db).load([item])
    return ctx.admin(item)


@router.post("/{item_id}/renormalize", response_model=ItemAdminOut)
async def renormalize(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.auction)))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    item.extraction_attempts = 0
    item.extraction_status = "pending"
    source = await db.get(Source, item.source_id)
    categories = (await db.execute(select(Category))).scalars().all()
    try:
        await normalize_item(db, item, source, categories)
    except LLMUnavailable as exc:
        await db.rollback()
        raise HTTPException(503, f"LLM indisponível: {exc}")
    await db.commit()
    await db.refresh(item)
    ctx = await SerializerContext(db).load([item])
    return ctx.admin(item)


@router.post("/{item_id}/publish", response_model=ItemAdminOut)
async def publish(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.auction)))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    item.status = "published"
    item.published_at = item.published_at or now_brt()
    if item.extraction_status != "done":
        item.extraction_status = "done"
        item.extraction_version = (item.extraction_version or "") + "+manual"
    await db.commit()
    await db.refresh(item)
    ctx = await SerializerContext(db).load([item])
    return ctx.admin(item)


@router.post("/{item_id}/hide", response_model=ItemAdminOut)
async def hide(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.auction)))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    item.status = "withdrawn"
    await db.commit()
    await db.refresh(item)
    ctx = await SerializerContext(db).load([item])
    return ctx.admin(item)


@router.delete("/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404, "Item não encontrado")
    await db.delete(item)
    await db.commit()
    return {"status": "ok"}
