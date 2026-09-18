import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.engine.lifecycle import VISIBLE_STATUSES
from app.models import Item, ScrapeIncident, Source
from app.schemas import SourceCreate, SourceOut, SourceTestOut, SourceUpdate
from app.scrapers import available_parsers, get_scraper

logger = logging.getLogger("zleilao.sources")
router = APIRouter()


async def _out(db: AsyncSession, s: Source) -> SourceOut:
    dto = SourceOut.model_validate(s)
    dto.items_total = await db.scalar(select(func.count(Item.id)).where(Item.source_id == s.id)) or 0
    dto.items_published = await db.scalar(select(func.count(Item.id)).where(Item.source_id == s.id, Item.status.in_(VISIBLE_STATUSES))) or 0
    dto.open_incidents = await db.scalar(select(func.count(ScrapeIncident.id)).where(ScrapeIncident.source_id == s.id, ScrapeIncident.status == "open")) or 0
    return dto


@router.get("", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    return [await _out(db, s) for s in rows]


@router.get("/parsers")
async def parsers():
    return available_parsers()


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(data: SourceCreate, db: AsyncSession = Depends(get_db)):
    try:
        cls = get_scraper(data.parser_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    dump = data.model_dump()
    if not dump.get("config"):
        dump["config"] = dict(cls.default_config)
    if await db.scalar(select(Source).where(Source.slug == dump["slug"])):
        raise HTTPException(409, "Já existe uma fonte com este slug")
    s = Source(**dump)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return await _out(db, s)


@router.get("/{source_id}", response_model=SourceOut)
async def get_source(source_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(Source, source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    return await _out(db, s)


@router.put("/{source_id}", response_model=SourceOut)
async def update_source(source_id: int, data: SourceUpdate, db: AsyncSession = Depends(get_db)):
    s = await db.get(Source, source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return await _out(db, s)


@router.delete("/{source_id}")
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(Source, source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    total = await db.scalar(select(func.count(Item.id)).where(Item.source_id == s.id)) or 0
    if total:
        raise HTTPException(409, f"Fonte possui {total} itens. Desative-a em vez de excluir.")
    await db.delete(s)
    await db.commit()
    return {"status": "ok"}


@router.post("/{source_id}/run")
async def run_source(source_id: int, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if not await db.get(Source, source_id):
        raise HTTPException(404, "Fonte não encontrada")

    async def _run():
        from app.scheduler.jobs import run_scrape_job
        async with AsyncSessionLocal() as session:
            await run_scrape_job(session, source_id)

    background.add_task(_run)
    return {"status": "started", "source_id": source_id}


@router.post("/{source_id}/test", response_model=SourceTestOut)
async def test_source(source_id: int, db: AsyncSession = Depends(get_db)):
    """Roda o parser a seco (sem gravar) e devolve uma amostra. Limita a 1 pagina e sem detalhes."""
    s = await db.get(Source, source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    from app.scheduler.jobs import run_scrape_job

    original = dict(s.config or {})
    s.config = {**original, "max_pages": 1, "fetch_details": False, "per_auction": False, "max_auctions": 0}
    try:
        res = await run_scrape_job(db, source_id, dry_run=True)
    finally:
        s.config = original
        await db.rollback()
    return SourceTestOut(ok=res.get("ok", False), items_found=res.get("items_found", 0), sample=res.get("sample", []),
                         error=res.get("error"), duration_ms=res.get("duration_ms", 0))


@router.post("/{source_id}/reactivate")
async def reactivate_source(source_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(Source, source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    s.health_status = "ok"
    s.suspended_reason = None
    await db.commit()
    return {"status": "ok"}
