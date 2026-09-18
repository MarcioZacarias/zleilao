from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, CategoryField, Item
from app.schemas import (
    CategoryCreate, CategoryFieldCreate, CategoryFieldOut, CategoryFieldUpdate, CategoryOut, CategoryTreeOut, CategoryUpdate,
)
from app.v1.serializers import SerializerContext

router = APIRouter()


async def _tree(db: AsyncSession) -> list[CategoryTreeOut]:
    cats = (await db.execute(select(Category).order_by(Category.sort_order, Category.id))).scalars().all()
    counts = dict((await db.execute(select(Item.category_id, func.count(Item.id)).group_by(Item.category_id))).all())
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
    roots = []
    for c in cats:
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id].children.append(nodes[c.id])
        else:
            roots.append(nodes[c.id])
    return roots


@router.get("", response_model=list[CategoryTreeOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await _tree(db)


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(Category).where(Category.slug == data.slug)):
        raise HTTPException(409, "Slug já existe")
    parent = await db.get(Category, data.parent_id) if data.parent_id else None
    if data.parent_id and not parent:
        raise HTTPException(404, "Categoria-mãe não encontrada")
    c = Category(**data.model_dump(), path=f"{parent.path}/{data.slug}" if parent else data.slug)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return CategoryOut(**{k: getattr(c, k) for k in ("id", "name", "slug", "parent_id", "is_active", "sort_order", "keywords", "llm_hint", "path", "created_at")}, fields=[])


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(category_id: int, data: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    c = await db.get(Category, category_id)
    if not c:
        raise HTTPException(404, "Categoria não encontrada")
    changes = data.model_dump(exclude_unset=True)
    old_path = c.path
    for k, v in changes.items():
        setattr(c, k, v)
    if "slug" in changes or "parent_id" in changes:
        parent = await db.get(Category, c.parent_id) if c.parent_id else None
        c.path = f"{parent.path}/{c.slug}" if parent else c.slug
        # atualiza descendentes
        for child in (await db.execute(select(Category).where(Category.path.like(f"{old_path}/%")))).scalars().all():
            child.path = c.path + child.path[len(old_path):]
    await db.commit()
    await db.refresh(c)
    return CategoryOut(**{k: getattr(c, k) for k in ("id", "name", "slug", "parent_id", "is_active", "sort_order", "keywords", "llm_hint", "path", "created_at")}, fields=[])


@router.delete("/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    c = await db.get(Category, category_id)
    if not c:
        raise HTTPException(404, "Categoria não encontrada")
    if await db.scalar(select(func.count(Item.id)).where(Item.category_id == c.id)):
        raise HTTPException(409, "Categoria possui itens. Desative-a em vez de excluir.")
    if await db.scalar(select(func.count(Category.id)).where(Category.parent_id == c.id)):
        raise HTTPException(409, "Categoria possui subcategorias.")
    await db.delete(c)
    await db.commit()
    return {"status": "ok"}


@router.get("/{category_id}/fields", response_model=list[CategoryFieldOut])
async def list_fields(category_id: int, db: AsyncSession = Depends(get_db)):
    c = await db.get(Category, category_id)
    if not c:
        raise HTTPException(404, "Categoria não encontrada")
    ctx = SerializerContext(db)
    ctx.categories = {c.id: c}
    await ctx.fields_for(c.id)
    return ctx.field_defs_out(c.id)


@router.post("/{category_id}/fields", response_model=CategoryFieldOut, status_code=201)
async def create_field(category_id: int, data: CategoryFieldCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Category, category_id):
        raise HTTPException(404, "Categoria não encontrada")
    if await db.scalar(select(CategoryField).where(CategoryField.category_id == category_id, CategoryField.key == data.key)):
        raise HTTPException(409, "Já existe campo com esta chave nesta categoria")
    f = CategoryField(category_id=category_id, **data.model_dump())
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return CategoryFieldOut.model_validate(f)


@router.put("/fields/{field_id}", response_model=CategoryFieldOut)
async def update_field(field_id: int, data: CategoryFieldUpdate, db: AsyncSession = Depends(get_db)):
    f = await db.get(CategoryField, field_id)
    if not f:
        raise HTTPException(404, "Campo não encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    await db.commit()
    await db.refresh(f)
    return CategoryFieldOut.model_validate(f)


@router.delete("/fields/{field_id}")
async def delete_field(field_id: int, db: AsyncSession = Depends(get_db)):
    f = await db.get(CategoryField, field_id)
    if not f:
        raise HTTPException(404, "Campo não encontrado")
    await db.delete(f)
    await db.commit()
    return {"status": "ok"}
