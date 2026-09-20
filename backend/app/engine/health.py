"""RN-008 — saude da coleta.

Parser que devolve 0 itens, ou variacao anormal vs. a media movel, gera
incidente e (se configurado) suspende a PUBLICACAO da fonte ate alguem
resolver no admin. A coleta continua, para acumular evidencia.

**Novo patamar.** A RN-008 existe para detectar quebra de parser, nao para
brigar com mudanca legitima de volume. Se o volume mudou de patamar e se
manteve estavel nas ultimas coletas, isso e' o novo normal: a media se
recalibra e o incidente aberto se auto-resolve. Sem isso a fonte fica presa
para sempre — medida em producao: Freitas coletou 24 itens por 40 horas
seguidas contra uma media congelada em 12, suspensa o tempo todo.
"""
from __future__ import annotations

import logging
import statistics

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobExecution, ScrapeIncident, Source
from app.settings_service import get_setting_bool, get_setting_float, get_setting_int
from app.timeutil import now_brt

logger = logging.getLogger("zleilao.health")

EMA_ALPHA = 0.3
#: coletas consecutivas com volume estavel que caracterizam um novo patamar
PLATEAU_RUNS = 3


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


async def _auto_resolve(db: AsyncSession, source: Source, kind: str, reason: str) -> None:
    """Fecha incidentes abertos de um tipo e reativa a fonte se nao sobrar nenhum."""
    open_ones = (await db.execute(select(ScrapeIncident).where(
        ScrapeIncident.source_id == source.id, ScrapeIncident.kind == kind, ScrapeIncident.status == "open"
    ))).scalars().all()
    for inc in open_ones:
        inc.status = "resolved"
        inc.resolved_at = now_brt()
        inc.resolved_by = "sistema"
        inc.message = f"{inc.message} — resolvido automaticamente: {reason}"[:1000]
    if not open_ones:
        return
    remaining = await db.scalar(select(func.count(ScrapeIncident.id)).where(
        ScrapeIncident.source_id == source.id, ScrapeIncident.status == "open"))
    if not remaining:
        source.health_status = "ok"
        source.suspended_reason = None
    logger.info("[%s] incidente(s) de %s resolvidos automaticamente: %s", source.name, kind, reason)


async def recent_counts(db: AsyncSession, source_id: int, limit: int) -> list[int]:
    """Volumes das ultimas coletas bem-sucedidas, da mais recente para a mais antiga."""
    rows = (await db.execute(
        select(JobExecution.items_processed)
        .where(JobExecution.source_id == source_id, JobExecution.job_type == "scrape",
               JobExecution.status == "success")
        .order_by(JobExecution.started_at.desc()).limit(limit)
    )).scalars().all()
    return [r for r in rows if r is not None]


def is_stable(counts: list[int], tolerance_pct: float) -> bool:
    """Volumes consistentes entre si (nenhum foge da mediana do grupo)."""
    if len(counts) < PLATEAU_RUNS:
        return False
    sample = counts[:PLATEAU_RUNS]
    center = statistics.median(sample)
    if center <= 0:
        return False
    return all(abs(c - center) / center * 100 <= tolerance_pct for c in sample)


async def evaluate_run(db: AsyncSession, source: Source, count: int, failed: bool, error: str | None) -> None:
    """Chamado ao fim de cada coleta. A execucao ja' foi registrada em
    job_executions, entao `recent_counts` inclui esta coleta."""
    if failed:
        await open_incident(db, source, "parser_error", (error or "falha na coleta")[:500], observed=count)
        return
    if count == 0:
        await open_incident(db, source, "zero_items", "parser retornou 0 itens",
                            expected=source.avg_items_count, observed=0)
        return

    # Coletou de novo depois de um zero: o parser voltou.
    await _auto_resolve(db, source, "zero_items", f"a coleta voltou a trazer itens ({count})")
    await _auto_resolve(db, source, "parser_error", "a coleta voltou a concluir sem erro")

    min_hist = await get_setting_int(db, "incident_min_history", 3)
    pct = await get_setting_float(db, "incident_variation_pct", 60.0)
    good_runs = await db.scalar(select(func.count(JobExecution.id)).where(
        JobExecution.source_id == source.id, JobExecution.job_type == "scrape",
        JobExecution.status == "success")) or 0

    if source.avg_items_count and good_runs >= min_hist:
        variation = abs(count - source.avg_items_count) / source.avg_items_count * 100
        if variation > pct:
            recent = await recent_counts(db, source.id, PLATEAU_RUNS)
            if is_stable(recent, pct):
                # Mudou de patamar e ficou estavel: e' o novo normal.
                novo = statistics.median(recent[:PLATEAU_RUNS])
                anterior = source.avg_items_count
                source.avg_items_count = float(novo)
                await _auto_resolve(
                    db, source, "abnormal_variation",
                    f"volume estavel em {novo:.0f} itens nas ultimas {PLATEAU_RUNS} coletas (media anterior {anterior:.0f})",
                )
                logger.info("[%s] novo patamar de volume: %.0f (era %.0f)", source.name, novo, anterior)
                return
            await open_incident(
                db, source, "abnormal_variation",
                f"{count} itens vs. media {source.avg_items_count:.0f} (variacao {variation:.0f}% > {pct:.0f}%)",
                expected=source.avg_items_count, observed=count,
            )
            # media nao e' contaminada pela coleta anomala
            return

    source.avg_items_count = float(count) if not source.avg_items_count else (
        EMA_ALPHA * count + (1 - EMA_ALPHA) * source.avg_items_count
    )
    if source.health_status != "suspended":
        source.health_status = "ok"


async def resolve_incident(db: AsyncSession, incident: ScrapeIncident, by: str, reactivate: bool) -> None:
    """Resolucao manual pelo admin. Recalibra a media quando o incidente era de
    volume: o operador conferiu e disse que o volume atual esta' correto — sem
    recalibrar, a proxima coleta reabriria o mesmo incidente."""
    incident.status = "resolved"
    incident.resolved_at = now_brt()
    incident.resolved_by = by
    source = await db.get(Source, incident.source_id)
    if source and incident.kind == "abnormal_variation" and incident.observed:
        source.avg_items_count = float(incident.observed)
        logger.info("[%s] media recalibrada para %.0f ao resolver incidente", source.name, incident.observed)
    still_open = await db.scalar(select(func.count(ScrapeIncident.id)).where(
        ScrapeIncident.source_id == incident.source_id, ScrapeIncident.status == "open",
        ScrapeIncident.id != incident.id))
    if reactivate and not still_open and source:
        source.health_status = "ok"
        source.suspended_reason = None
