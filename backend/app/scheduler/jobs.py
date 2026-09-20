"""Jobs de fundo (APScheduler, AsyncIOScheduler).

  scrape_tick  — a cada N min: coleta as fontes ativas que estao "vencidas"
  normalize    — a cada M min: extrai campos dos itens pendentes (LLM/regras)
  lifecycle    — a cada L min: publica, marca pregao proximo, encerra, oculta
  dedup        — a cada D min: vinculos suspeitos entre fontes (RN-004)
  cleanup      — diario 03:00 BRT: retencao de raw_items e encerrados

Intervalos vem da tabela settings e sao lidos NO BOOT (mudar => restart).
Cada job tem max_instances=1: um ciclo lento nunca sobrepoe o proximo.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.timeutil import BRT, now_brt
from app.engine.dedup import run_dedup
from app.engine.health import evaluate_run, open_incident
from app.engine.lifecycle import run_cleanup, run_lifecycle
from app.engine.normalizer import LLMUnavailable, normalize_item
from app.models import (
    Auction, AuctionSession, Category, Item, ItemPriceHistory, JobExecution, RawItem, Source,
)
from app.scrapers import ScrapedItem, get_scraper
from app.scrapers.robots import robots_allows
from app.settings_service import (
    get_setting, get_setting_bool, get_setting_float, get_setting_int,
)

logger = logging.getLogger("zleilao.scheduler")

_scheduler: AsyncIOScheduler | None = None
_locks: dict[str, asyncio.Lock] = {}


def _lock(name: str) -> asyncio.Lock:
    return _locks.setdefault(name, asyncio.Lock())


async def start_scheduler() -> None:
    global _scheduler
    async with AsyncSessionLocal() as db:
        tick = await get_setting_int(db, "scrape_tick_minutes", 10)
        norm = await get_setting_int(db, "normalize_interval_minutes", 5)
        life = await get_setting_int(db, "lifecycle_interval_minutes", 30)
        dedup = await get_setting_int(db, "dedup_interval_minutes", 60)
    # Datas de inicio timezone-aware: o container roda em UTC e o scheduler em
    # Brasilia; um `datetime.now()` naive seria interpretado no fuso errado.
    boot = datetime.now(BRT)
    # coalesce + misfire_grace_time: se a maquina suspende ou o processo demora
    # a subir, o job roda assim que possivel em vez de ser pulado em silencio.
    # Medido: a limpeza das 03:00 foi perdida por 7h20 numa hibernacao.
    _scheduler = AsyncIOScheduler(
        timezone=BRT,
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
    )
    _scheduler.add_job(scrape_tick, IntervalTrigger(minutes=max(1, tick), start_date=boot + timedelta(seconds=20), timezone=BRT),
                       id="scrape_tick", max_instances=1, coalesce=True)
    _scheduler.add_job(normalize_job, IntervalTrigger(minutes=max(1, norm), start_date=boot + timedelta(seconds=60), timezone=BRT),
                       id="normalize", max_instances=1, coalesce=True)
    _scheduler.add_job(lifecycle_job, IntervalTrigger(minutes=max(1, life), start_date=boot + timedelta(seconds=90), timezone=BRT),
                       id="lifecycle", max_instances=1, coalesce=True)
    _scheduler.add_job(dedup_job, IntervalTrigger(minutes=max(5, dedup), start_date=boot + timedelta(minutes=5), timezone=BRT),
                       id="dedup", max_instances=1, coalesce=True)
    _scheduler.add_job(cleanup_job, CronTrigger(hour=3, minute=0, timezone=BRT), id="cleanup", max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info("Scheduler: scrape_tick %dm, normalize %dm, lifecycle %dm, dedup %dm, cleanup 03:00", tick, norm, life, dedup)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_status() -> list[dict[str, Any]]:
    if not _scheduler:
        return []
    return [
        {"id": j.id, "next_run_at": j.next_run_time.astimezone(BRT).replace(tzinfo=None).isoformat() if j.next_run_time else None,
         "running": _lock(j.id).locked()}
        for j in _scheduler.get_jobs()
    ]


# ── helpers de job ──────────────────────────────────────────────────

async def _start_job(db: AsyncSession, job_type: str, source_id: int | None = None) -> JobExecution:
    job = JobExecution(job_type=job_type, source_id=source_id, status="running", started_at=now_brt())
    db.add(job)
    await db.commit()
    return job


async def _finish_job(db: AsyncSession, job: JobExecution, status: str, processed: int = 0,
                      error: str | None = None, details: dict | None = None) -> None:
    job.status = status
    job.items_processed = processed
    job.error = error[:1000] if error else None
    job.details = details
    job.finished_at = now_brt()
    await db.commit()


def _hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str, ensure_ascii=False).encode())
        h.update(b"|")
    return h.hexdigest()


# ── SCRAPE ──────────────────────────────────────────────────────────

def _is_due(source: Source) -> bool:
    if not source.last_run_at:
        return True
    return now_brt() - source.last_run_at >= timedelta(minutes=source.scrape_frequency or 240)


async def scrape_tick() -> None:
    if _lock("scrape_tick").locked():
        return
    async with _lock("scrape_tick"):
        async with AsyncSessionLocal() as db:
            sources = (await db.execute(select(Source).where(Source.is_active.is_(True)).order_by(Source.priority_weight.desc()))).scalars().all()
            due = [s.id for s in sources if _is_due(s)]
        for sid in due:
            async with AsyncSessionLocal() as db:
                try:
                    await run_scrape_job(db, sid)
                except Exception as exc:
                    logger.exception("scrape da fonte %s falhou: %s", sid, exc)


async def _runtime(db: AsyncSession) -> dict[str, Any]:
    return {
        "user_agent": await get_setting(db, "scraper_user_agent", ""),
        "request_delay_min": await get_setting_float(db, "request_delay_min", 1.0),
        "request_delay_max": await get_setting_float(db, "request_delay_max", 3.0),
        "fetch_details_default": await get_setting_bool(db, "fetch_details_default", True),
        "max_details_per_run": await get_setting_int(db, "max_details_per_run", 60),
    }


async def run_scrape_job(db: AsyncSession, source_id: int, dry_run: bool = False) -> dict[str, Any]:
    source = await db.get(Source, source_id)
    if not source:
        return {"ok": False, "error": "fonte nao encontrada"}
    runtime = await _runtime(db)

    # RN-009: flag do cadastro + robots.txt
    if not source.scraping_allowed:
        if not dry_run:
            await open_incident(db, source, "scraping_not_allowed", "fonte marcada como scraping_allowed=false")
            source.last_run_status = "skipped"
            await db.commit()
        return {"ok": False, "error": "scraping_allowed=false"}
    if await get_setting_bool(db, "respect_robots", True) and source.base_url:
        allowed, status = await robots_allows(source.base_url, runtime["user_agent"] or "*", "/")
        source.robots_status, source.robots_checked_at = status, now_brt()
        if not allowed:
            if not dry_run:
                await open_incident(db, source, "robots_disallowed", "robots.txt proibe a coleta")
                source.last_run_status = "skipped"
                await db.commit()
            return {"ok": False, "error": "robots.txt proibe"}

    job = None if dry_run else await _start_job(db, "scrape", source.id)
    started = now_brt()
    try:
        scraper_cls = get_scraper(source.parser_type)
        scraper = scraper_cls(source_id=source.id, base_url=source.base_url, config=source.config or {}, runtime=runtime)
        async with scraper:
            scraped = await scraper.run()
        stats = scraper.stats
    except Exception as exc:
        logger.exception("[%s] coleta falhou: %s", source.name, exc)
        if not dry_run:
            source.last_run_at = now_brt()
            source.last_run_status = "failed"
            await evaluate_run(db, source, 0, True, str(exc))
            await _finish_job(db, job, "failed", 0, str(exc))
        return {"ok": False, "error": str(exc)}

    if dry_run:
        return {
            "ok": True, "items_found": len(scraped),
            "sample": [_sample(s) for s in scraped[:5]],
            "duration_ms": int((now_brt() - started).total_seconds() * 1000),
            "complete": stats.complete,
            "stats": stats.__dict__,
        }

    count = await persist_scraped(db, source, scraped, complete=stats.complete)
    source.last_run_at = now_brt()
    source.last_run_status = "success"
    source.last_items_count = count
    await evaluate_run(db, source, count, False, None)
    await _finish_job(db, job, "success", count, details={
        "pages": stats.pages, "details": stats.details, "errors": stats.errors,
        "complete": stats.complete, "notes": stats.notes,
    })
    logger.info("[%s] coleta concluida: %d itens", source.name, count)
    return {"ok": True, "items_found": count}


def _sample(s: ScrapedItem) -> dict[str, Any]:
    return {
        "external_id": s.external_id, "title": s.title, "price": str(s.price) if s.price is not None else None,
        "city": s.city, "state": s.state, "official_url": s.official_url, "image_url": s.image_url,
        "status_hint": s.status_hint, "category_hint": s.category_hint,
        "sessions": [{"kind": x.kind, "starts_at": x.starts_at.isoformat() if x.starts_at else None} for x in (s.auction.sessions if s.auction else [])],
        "raw_attributes": s.raw_attributes,
    }


def _fit(val: Any, n: int | None) -> Any:
    """Trunca strings ao tamanho da coluna (fontes mandam textos imprevisiveis)
    e normaliza string vazia para None — vazio nao e' dado, e' ausencia."""
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
    if n is None:
        return val
    sv = str(val)
    return sv[:n] if len(sv) > n else sv


AUCTION_LIMITS = {"title": None, "auctioneer_name": 200, "auctioneer_registration": 200, "committer_name": 200,
                  "modality": 20, "auction_type": 20, "official_url": None}


async def _upsert_auction(db: AsyncSession, source_id: int, scraped: ScrapedItem) -> Auction | None:
    a = scraped.auction
    if not a:
        return None
    ext = _fit(a.external_id, 200)
    auction = await db.scalar(select(Auction).where(Auction.source_id == source_id, Auction.external_id == ext))
    if not auction:
        auction = Auction(source_id=source_id, external_id=ext)
        db.add(auction)
        await db.flush()
    for attr, n in AUCTION_LIMITS.items():
        val = getattr(a, attr)
        if val:
            setattr(auction, attr, _fit(val, n))
    if a.sessions:
        existing = (await db.execute(select(AuctionSession).where(AuctionSession.auction_id == auction.id))).scalars().all()
        by_kind = {s.kind: s for s in existing}
        for seq, s in enumerate(a.sessions, start=1):
            row = by_kind.get(s.kind)
            if not row:
                row = AuctionSession(auction_id=auction.id, kind=s.kind, sequence=seq)
                db.add(row)
            row.sequence = seq
            if s.starts_at:
                row.starts_at = s.starts_at
            if s.ends_at:
                row.ends_at = s.ends_at
            if s.min_bid is not None:
                row.min_bid = s.min_bid
    return auction


async def _persist_one(db: AsyncSession, source_id: int, s: ScrapedItem, now: datetime) -> None:
    auction = await _upsert_auction(db, source_id, s)
    ext_id = _fit(s.external_id, 200)
    item = await db.scalar(select(Item).where(Item.source_id == source_id, Item.external_id == ext_id))
    chash = _hash(s.title, s.description, str(s.price), str(s.price_second), s.raw_attributes, s.status_hint,
                  [(x.kind, str(x.starts_at)) for x in (s.auction.sessions if s.auction else [])])
    attrs_seed = {"_raw": s.raw_attributes or {}, "_category_hint": s.category_hint}
    common = dict(
        title=s.title, lot_number=_fit(s.lot_number, 50), price=s.price, price_kind=_fit(s.price_kind, 20),
        price_second=s.price_second, city=_fit(s.city, 120), state=_fit(s.state, 2), location_text=s.location_text,
    )
    if not item:
        item = Item(
            item_type="lot", source_id=source_id, external_id=ext_id, auction_id=auction.id if auction else None,
            description=s.description, official_url=s.official_url, image_url=s.image_url, images=s.images or [],
            attributes=attrs_seed, status="collected", status_hint=_fit(s.status_hint, 20), extraction_status="pending",
            content_hash=chash, first_seen_at=now, last_seen_at=now, **common,
        )
        db.add(item)
        await db.flush()
        if s.price is not None:
            db.add(ItemPriceHistory(item_id=item.id, price=s.price, price_kind=s.price_kind, observed_at=now))
        changed = True
    else:
        changed = item.content_hash != chash
        old_price = item.price
        item.last_seen_at = now
        item.misses = 0
        item.status_hint = _fit(s.status_hint, 20) or item.status_hint
        item.official_url = s.official_url or item.official_url
        item.image_url = s.image_url or item.image_url
        if s.images:
            item.images = s.images
        item.auction_id = auction.id if auction else item.auction_id
        if changed:
            # Texto novo => reextrair. A fonte manda sobre edicoes manuais.
            for k, v in common.items():
                if v is not None or k in ("price", "price_second"):
                    setattr(item, k, v)
            if s.description:
                item.description = s.description
            attrs = dict(item.attributes or {})
            attrs.update(attrs_seed)
            item.attributes = attrs
            item.content_hash = chash
            if item.extraction_status in ("done", "skipped"):
                item.extraction_status = "pending"
                item.extraction_attempts = 0
            if s.price is not None and s.price != old_price:
                db.add(ItemPriceHistory(item_id=item.id, price=s.price, price_kind=s.price_kind, observed_at=now))
        # Reabertura: o lote reapareceu, ou a fonte voltou a declara-lo aberto
        # (repasse/condicional negada apos a sessao). A fonte manda.
        reopen = item.status == "possibly_withdrawn" or (item.status == "closed" and s.status_hint == "open")
        if reopen:
            item.status = "published" if item.extraction_status == "done" else "collected"
            item.closed_at = None
    if changed and s.raw_payload:
        last = await db.scalar(select(RawItem.content_hash).where(
            RawItem.source_id == source_id, RawItem.external_id == ext_id).order_by(RawItem.fetched_at.desc()).limit(1))
        if last != chash:
            db.add(RawItem(source_id=source_id, external_id=ext_id, content_hash=chash, payload=s.raw_payload[:200_000], fetched_at=now))


async def persist_scraped(db: AsyncSession, source: Source, scraped: list[ScrapedItem], complete: bool = True) -> int:
    """Um SAVEPOINT por item: um lote quebrado nao derruba a coleta da fonte."""
    now = now_brt()
    source_id, source_name = source.id, source.name
    seen_ids: set[str] = set()
    count = 0
    for s in scraped:
        try:
            async with db.begin_nested():
                await _persist_one(db, source_id, s, now)
            seen_ids.add(_fit(s.external_id, 200))
            count += 1
            if count % 25 == 0:
                await db.commit()
        except Exception as exc:
            logger.warning("[%s] item %s nao persistido: %s", source_name, s.external_id, str(exc)[:300])
    # RN-005: nao reencontrados. Só conta quando a varredura viu o catálogo
    # inteiro — numa coleta parcial (limite de páginas, paginação client-side)
    # o item pode estar apenas fora da janela vista, e marcá-lo como retirado
    # esconderia da vitrine um lote que existe. Medido: 76 lotes sumiram assim.
    if seen_ids and complete:
        missing = (await db.execute(select(Item).where(
            Item.source_id == source_id, Item.status.notin_(("closed", "withdrawn")), Item.external_id.notin_(seen_ids)))).scalars().all()
        for it in missing:
            it.misses += 1
    elif seen_ids:
        logger.info("[%s] varredura parcial: ausencias nao contam como retirada", source_name)
    await db.commit()
    return count


# ── NORMALIZE ───────────────────────────────────────────────────────

async def normalize_job() -> dict[str, Any]:
    if _lock("normalize").locked():
        return {"skipped": True}
    async with _lock("normalize"):
        async with AsyncSessionLocal() as db:
            job = await _start_job(db, "normalize")
            llm_on = await get_setting_bool(db, "llm_enabled", True) and bool(await get_setting(db, "llm_api_key", ""))
            limit = await get_setting_int(db, "llm_max_items_per_cycle", 40) if llm_on else 500
            max_attempts = await get_setting_int(db, "extraction_max_attempts", 2)
            categories = (await db.execute(select(Category))).scalars().all()
            items = (await db.execute(
                select(Item).where(Item.extraction_status.in_(("pending", "failed")), Item.extraction_attempts < max_attempts)
                .order_by(Item.first_seen_at.desc()).limit(limit)
            )).scalars().all()
            sources = {s.id: s for s in (await db.execute(select(Source))).scalars().all()}
            done = failed = review = 0
            stopped: str | None = None
            for it in items:
                try:
                    status = await normalize_item(db, it, sources[it.source_id], categories)
                    await db.commit()
                    if status == "done":
                        done += 1
                    elif status == "review":
                        review += 1
                    else:
                        failed += 1
                except LLMUnavailable as exc:
                    await db.rollback()
                    stopped = str(exc)
                    logger.warning("normalize interrompido: %s", exc)
                    break
                except Exception as exc:
                    await db.rollback()
                    failed += 1
                    logger.exception("normalize item %s: %s", it.id, exc)
            details = {"done": done, "failed": failed, "review": review, "llm": llm_on, "stopped": stopped}
            await _finish_job(db, job, "success" if not stopped else "failed", done, stopped, details)
            return details


# ── LIFECYCLE / DEDUP / CLEANUP ─────────────────────────────────────

async def lifecycle_job() -> dict[str, Any]:
    if _lock("lifecycle").locked():
        return {"skipped": True}
    async with _lock("lifecycle"):
        async with AsyncSessionLocal() as db:
            job = await _start_job(db, "lifecycle")
            try:
                stats = await run_lifecycle(db)
                await _finish_job(db, job, "success", sum(stats.values()), details=stats)
                return stats
            except Exception as exc:
                await db.rollback()
                await _finish_job(db, job, "failed", 0, str(exc))
                raise


async def dedup_job() -> dict[str, Any]:
    if _lock("dedup").locked():
        return {"skipped": True}
    async with _lock("dedup"):
        async with AsyncSessionLocal() as db:
            if not await get_setting_bool(db, "dedup_enabled", True):
                return {"disabled": True}
            job = await _start_job(db, "dedup")
            try:
                threshold = await get_setting_float(db, "dedup_threshold", 0.85)
                created = await run_dedup(db, threshold)
                await _finish_job(db, job, "success", created, details={"created": created, "threshold": threshold})
                return {"created": created}
            except Exception as exc:
                await db.rollback()
                await _finish_job(db, job, "failed", 0, str(exc))
                raise


async def cleanup_job() -> dict[str, Any]:
    async with _lock("cleanup"):
        async with AsyncSessionLocal() as db:
            job = await _start_job(db, "cleanup")
            try:
                stats = await run_cleanup(db)
                await _finish_job(db, job, "success", sum(stats.values()), details=stats)
                return stats
            except Exception as exc:
                await db.rollback()
                await _finish_job(db, job, "failed", 0, str(exc))
                raise


JOB_RUNNERS = {
    "scrape_tick": scrape_tick,
    "normalize": normalize_job,
    "lifecycle": lifecycle_job,
    "dedup": dedup_job,
    "cleanup": cleanup_job,
}
