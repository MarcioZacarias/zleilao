"""Incidentes (RN-008), jobs, duplicados (RN-004) e dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.timeutil import now_brt
from app.database import get_db
from app.engine.health import resolve_incident
from app.engine.lifecycle import VISIBLE_STATUSES
from app.models import Auction, ClickEvent, Item, ItemDuplicate, JobExecution, ScrapeIncident, Source, User
from app.schemas import DuplicateOut, DuplicateUpdate, IncidentOut, IncidentUpdate, JobExecutionOut
from app.v1.serializers import SerializerContext

incidents_router = APIRouter()
jobs_router = APIRouter()
duplicates_router = APIRouter()
dashboard_router = APIRouter()


# ── incidentes ─────────────────────────────────────────────────────

@incidents_router.get("", response_model=list[IncidentOut])
async def list_incidents(status: Optional[str] = Query("open"), source_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ScrapeIncident, Source.name).join(Source, Source.id == ScrapeIncident.source_id)
    if status and status != "all":
        stmt = stmt.where(ScrapeIncident.status.in_(status.split(",")))
    if source_id:
        stmt = stmt.where(ScrapeIncident.source_id == source_id)
    rows = (await db.execute(stmt.order_by(ScrapeIncident.created_at.desc()).limit(300))).all()
    out = []
    for inc, name in rows:
        dto = IncidentOut.model_validate(inc)
        dto.source_name = name
        out.append(dto)
    return out


@incidents_router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(incident_id: int, data: IncidentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    inc = await db.get(ScrapeIncident, incident_id)
    if not inc:
        raise HTTPException(404, "Incidente não encontrado")
    if data.status == "resolved":
        await resolve_incident(db, inc, user.email, data.reactivate_source)
    elif data.status == "acknowledged":
        inc.status = "acknowledged"
    else:
        raise HTTPException(400, "status deve ser acknowledged ou resolved")
    await db.commit()
    await db.refresh(inc)
    dto = IncidentOut.model_validate(inc)
    dto.source_name = (await db.get(Source, inc.source_id)).name
    return dto


# ── jobs ───────────────────────────────────────────────────────────

@jobs_router.get("", response_model=list[JobExecutionOut])
async def list_jobs(job_type: Optional[str] = None, limit: int = Query(100, le=500), db: AsyncSession = Depends(get_db)):
    stmt = select(JobExecution, Source.name).outerjoin(Source, Source.id == JobExecution.source_id)
    if job_type:
        stmt = stmt.where(JobExecution.job_type == job_type)
    rows = (await db.execute(stmt.order_by(JobExecution.started_at.desc()).limit(limit))).all()
    out = []
    for job, name in rows:
        dto = JobExecutionOut.model_validate(job)
        dto.source_name = name
        out.append(dto)
    return out


@jobs_router.get("/scheduler")
async def scheduler():
    from app.scheduler.jobs import scheduler_status
    return {"jobs": scheduler_status()}


@jobs_router.post("/{job_type}/run")
async def run_job(job_type: str, background: BackgroundTasks):
    from app.scheduler.jobs import JOB_RUNNERS
    runner = JOB_RUNNERS.get(job_type)
    if not runner:
        raise HTTPException(404, f"Job desconhecido. Disponíveis: {list(JOB_RUNNERS)}")
    background.add_task(runner)
    return {"status": "started", "job_type": job_type}


# ── duplicados ─────────────────────────────────────────────────────

@duplicates_router.get("", response_model=list[DuplicateOut])
async def list_duplicates(status: Optional[str] = Query("suspected"), limit: int = Query(100, le=500), db: AsyncSession = Depends(get_db)):
    stmt = select(ItemDuplicate)
    if status and status != "all":
        stmt = stmt.where(ItemDuplicate.status.in_(status.split(",")))
    dups = (await db.execute(stmt.order_by(ItemDuplicate.similarity.desc(), ItemDuplicate.created_at.desc()).limit(limit))).scalars().all()
    ids = {d.canonical_item_id for d in dups} | {d.duplicate_item_id for d in dups}
    items = {i.id: i for i in (await db.execute(select(Item).where(Item.id.in_(ids)).options(selectinload(Item.auction)))).scalars().all()} if ids else {}
    ctx = await SerializerContext(db).load(list(items.values()))
    out = []
    for d in dups:
        a, b = items.get(d.canonical_item_id), items.get(d.duplicate_item_id)
        if a and b:
            out.append(DuplicateOut(id=d.id, canonical=ctx.card(a), duplicate=ctx.card(b), similarity=d.similarity,
                                    reasons=d.reasons, status=d.status, created_at=d.created_at))
    return out


@duplicates_router.patch("/{dup_id}")
async def update_duplicate(dup_id: int, data: DuplicateUpdate, db: AsyncSession = Depends(get_db)):
    d = await db.get(ItemDuplicate, dup_id)
    if not d:
        raise HTTPException(404, "Vínculo não encontrado")
    if data.status not in ("confirmed", "rejected", "suspected"):
        raise HTTPException(400, "status inválido")
    d.status = data.status
    d.reviewed_at = now_brt()
    await db.commit()
    return {"status": "ok", "id": d.id, "new_status": d.status}


# ── dashboard ──────────────────────────────────────────────────────

@dashboard_router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    now = now_brt()
    by_status = dict((await db.execute(select(Item.status, func.count()).group_by(Item.status))).all())
    by_extraction = dict((await db.execute(select(Item.extraction_status, func.count()).group_by(Item.extraction_status))).all())
    total_items = sum(by_status.values())
    sources = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    per_source_total = dict((await db.execute(select(Item.source_id, func.count()).group_by(Item.source_id))).all())
    per_source_pub = dict((await db.execute(select(Item.source_id, func.count()).where(Item.status.in_(VISIBLE_STATUSES)).group_by(Item.source_id))).all())
    clicks_7d = dict((await db.execute(
        select(ClickEvent.source_id, func.count()).where(ClickEvent.clicked_at >= now - timedelta(days=7)).group_by(ClickEvent.source_id)
    )).all())
    open_incidents = await db.scalar(select(func.count(ScrapeIncident.id)).where(ScrapeIncident.status == "open")) or 0
    suspected_dups = await db.scalar(select(func.count(ItemDuplicate.id)).where(ItemDuplicate.status == "suspected")) or 0
    new_24h = await db.scalar(select(func.count(Item.id)).where(Item.first_seen_at >= now - timedelta(hours=24))) or 0
    upcoming = await db.scalar(select(func.count(Auction.id)).where(Auction.starts_at >= now, Auction.starts_at <= now + timedelta(days=7))) or 0
    last_jobs = {}
    for jt in ("scrape", "normalize", "lifecycle", "dedup", "cleanup"):
        j = await db.scalar(select(JobExecution).where(JobExecution.job_type == jt).order_by(JobExecution.started_at.desc()).limit(1))
        last_jobs[jt] = JobExecutionOut.model_validate(j).model_dump() if j else None
    # coleta por dia (14 dias) para grafico
    daily = (await db.execute(
        select(func.date_trunc("day", Item.first_seen_at).label("d"), func.count()).where(Item.first_seen_at >= now - timedelta(days=14))
        .group_by("d").order_by("d")
    )).all()
    done = by_extraction.get("done", 0)
    return {
        "items_total": total_items,
        "items_by_status": by_status,
        "items_by_extraction": by_extraction,
        "extraction_rate": round(done / total_items, 3) if total_items else None,
        "items_new_24h": new_24h,
        "auctions_upcoming_7d": upcoming,
        "open_incidents": open_incidents,
        "suspected_duplicates": suspected_dups,
        "sources": [
            {
                "id": s.id, "name": s.name, "slug": s.slug, "is_active": s.is_active, "dispatch_enabled": s.dispatch_enabled,
                "health_status": s.health_status, "last_run_at": s.last_run_at, "last_run_status": s.last_run_status,
                "last_items_count": s.last_items_count, "avg_items_count": s.avg_items_count,
                "items_total": per_source_total.get(s.id, 0), "items_published": per_source_pub.get(s.id, 0),
                "clicks_7d": clicks_7d.get(s.id, 0),
                "ctr_7d": round(clicks_7d.get(s.id, 0) / per_source_pub[s.id], 4) if per_source_pub.get(s.id) else None,
            }
            for s in sources
        ],
        "last_jobs": last_jobs,
        "daily_collected": [{"day": d.date().isoformat() if hasattr(d, "date") else str(d), "count": c} for d, c in daily],
    }
