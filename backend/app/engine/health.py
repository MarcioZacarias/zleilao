"""RN-008 — saude da coleta.

Parser que devolve 0 itens, ou variacao anormal vs. media movel, gera
incidente e (se configurado) suspende a PUBLICACAO da fonte ate alguem
resolver no admin. A coleta continua (para acumular evidencia).
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobExecution, ScrapeIncident, Source
from app.timeutil import now_brt
from app.settings_service import get_setting_bool, get_setting_float, get_setting_int

logger = logging.getLogger("zleilao.health")

EMA_ALPHA = 0.3


async def open_incident(db: AsyncSession, source: Source, kind: str, message: str,
                        expected: float | None = None, observed: float | None = None) -> ScrapeIncident | None:
    # Nao duplica incidente aberto do mesmo tipo
    existing = await db.scalar(select(ScrapeIncident).where(
        ScrapeIncident.source_id == source.id, ScrapeIncident.kind == kind, ScrapeIncident.status == "open"))
    if existing:
        existing.message = message
        existing.observed = observed
        return None
    inc = ScrapeIncident(source_id=source.id, kind=kind, message=message, expected=expected, observed=observed)
    db.add(inc)
    if await get_setting_bool(db, "suspend_on_incident", True):
        source.health_status = "suspended"
        source.suspended_reason = f"{kind}: {message}"[:500]
    logger.warning("incidente [%s] em %s: %s", kind, source.name, message)
    return inc


async def evaluate_run(db: AsyncSession, source: Source, count: int, failed: bool, error: str | None) -> None:
    """Chamado ao fim de cada coleta."""
    if failed:
        await open_incident(db, source, "parser_error", (error or "falha na coleta")[:500], observed=count)
        return
    if count == 0:
        await open_incident(db, source, "zero_items", "parser retornou 0 itens", expected=source.avg_items_count, observed=0)
        return

    min_hist = await get_setting_int(db, "incident_min_history", 3)
    pct = await get_setting_float(db, "incident_variation_pct", 60.0)
    good_runs = await db.scalar(select(func.count(JobExecution.id)).where(
        JobExecution.source_id == source.id, JobExecution.job_type == "scrape", JobExecution.status == "success"))
    if source.avg_items_count and (good_runs or 0) >= min_hist:
        variation = abs(count - source.avg_items_count) / source.avg_items_count * 100
        if variation > pct:
            await open_incident(
                db, source, "abnormal_variation",
                f"{count} itens vs. media {source.avg_items_count:.0f} (variacao {variation:.0f}% > {pct:.0f}%)",
                expected=source.avg_items_count, observed=count,
            )
            # media nao e' atualizada com a coleta anomala
            return
    source.avg_items_count = count if not source.avg_items_count else (EMA_ALPHA * count + (1 - EMA_ALPHA) * source.avg_items_count)
    if source.health_status != "suspended":
        source.health_status = "ok"


async def resolve_incident(db: AsyncSession, incident: ScrapeIncident, by: str, reactivate: bool) -> None:
    incident.status = "resolved"
    incident.resolved_at = now_brt()
    incident.resolved_by = by
    still_open = await db.scalar(select(func.count(ScrapeIncident.id)).where(
        ScrapeIncident.source_id == incident.source_id, ScrapeIncident.status == "open", ScrapeIncident.id != incident.id))
    if reactivate and not still_open:
        source = await db.get(Source, incident.source_id)
        if source:
            source.health_status = "ok"
            source.suspended_reason = None
