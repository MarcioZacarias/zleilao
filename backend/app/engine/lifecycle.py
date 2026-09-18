"""RN-005 — ciclo de vida do item.

coletado -> publicado -> pregao_proximo (D-N) -> encerrado/retirado
Nao reencontrado em N coletas => possivelmente_retirado (oculto da vitrine).
Publicacao exige: extracao concluida, fonte com dispatch_enabled e sem
suspensao (RN-008).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, false, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Auction, AuctionSession, Item, RawItem, Source
from app.timeutil import now_brt
from app.settings_service import get_setting_int

logger = logging.getLogger("zleilao.lifecycle")

VISIBLE_STATUSES = ("published", "auction_soon")


async def run_lifecycle(db: AsyncSession) -> dict[str, int]:
    now = now_brt()
    soon_days = await get_setting_int(db, "auction_soon_days", 2)
    grace_h = await get_setting_int(db, "closed_grace_hours", 6)
    misses_threshold = await get_setting_int(db, "lifecycle_misses_threshold", 3)
    stats = {"published": 0, "auction_soon": 0, "back_to_published": 0, "closed": 0, "withdrawn": 0, "possibly_withdrawn": 0, "next_session": 0}

    # 1. next_session_at (denormalizado) — proxima sessao futura, senao a ultima
    items_with_auction = (await db.execute(
        select(Item).where(Item.auction_id.isnot(None), Item.status.notin_(("closed", "withdrawn")))
    )).scalars().all()
    auction_ids = {i.auction_id for i in items_with_auction}
    sessions_by_auction: dict[int, list[AuctionSession]] = {}
    if auction_ids:
        for s in (await db.execute(select(AuctionSession).where(AuctionSession.auction_id.in_(auction_ids)))).scalars().all():
            sessions_by_auction.setdefault(s.auction_id, []).append(s)
    for it in items_with_auction:
        sessions = sessions_by_auction.get(it.auction_id, [])
        starts = sorted([s.starts_at for s in sessions if s.starts_at])
        nxt = next((d for d in starts if d >= now - timedelta(hours=grace_h)), starts[-1] if starts else None)
        if nxt != it.next_session_at:
            it.next_session_at = nxt
            stats["next_session"] += 1

    # 2. Publicar coletados normalizados de fontes saudaveis
    ok_sources = {s.id for s in (await db.execute(
        select(Source).where(Source.dispatch_enabled.is_(True), Source.health_status != "suspended")
    )).scalars().all()}
    to_publish = (await db.execute(select(Item).where(
        Item.status == "collected", Item.extraction_status == "done", Item.source_id.in_(ok_sources) if ok_sources else false(),
    ))).scalars().all()
    for it in to_publish:
        if it.status_hint in ("closed", "sold"):
            it.status, it.closed_at = "closed", it.closed_at or now
            stats["closed"] += 1
            continue
        if it.status_hint == "withdrawn":
            it.status = "withdrawn"
            stats["withdrawn"] += 1
            continue
        it.status = "published"
        it.published_at = it.published_at or now
        stats["published"] += 1

    # 3. Encerramento / retirada / pregao proximo entre os visiveis
    visible = (await db.execute(select(Item).where(Item.status.in_(VISIBLE_STATUSES)))).scalars().all()
    soon_limit = now + timedelta(days=soon_days)
    for it in visible:
        if it.status_hint in ("closed", "sold"):
            it.status, it.closed_at = "closed", now
            stats["closed"] += 1
            continue
        if it.status_hint == "withdrawn":
            it.status = "withdrawn"
            stats["withdrawn"] += 1
            continue
        # A fonte tem a palavra final sobre o proprio lote: em leilao de
        # seguradora/financeira e comum o lote seguir disponivel DEPOIS da
        # sessao (repasse, lance condicional, condicional negada). Encerrar
        # por data esconderia da vitrine justamente a oportunidade ativa.
        # Sem esse guard, 35 dos 72 lotes do Leilo sumiam da busca.
        if it.status_hint != "open":
            sessions = sessions_by_auction.get(it.auction_id or -1, [])
            ends = [s.ends_at or s.starts_at for s in sessions if (s.ends_at or s.starts_at)]
            if ends and max(ends) + timedelta(hours=grace_h) < now:
                it.status, it.closed_at = "closed", now
                stats["closed"] += 1
                continue
        if it.misses >= misses_threshold:
            it.status = "possibly_withdrawn"
            stats["possibly_withdrawn"] += 1
            continue
        if it.next_session_at and now <= it.next_session_at <= soon_limit:
            if it.status != "auction_soon":
                it.status = "auction_soon"
                stats["auction_soon"] += 1
        elif it.status == "auction_soon":
            it.status = "published"
            stats["back_to_published"] += 1

    # 4. Status do pregao
    for auction in (await db.execute(select(Auction).where(Auction.status != "closed"))).scalars().all():
        sessions = sessions_by_auction.get(auction.id) or (await db.execute(
            select(AuctionSession).where(AuctionSession.auction_id == auction.id))).scalars().all()
        starts = [s.starts_at for s in sessions if s.starts_at]
        if not starts:
            continue
        auction.starts_at, auction.ends_at = min(starts), max(s.ends_at or s.starts_at for s in sessions if (s.ends_at or s.starts_at))
        if auction.ends_at and auction.ends_at + timedelta(hours=grace_h) < now:
            auction.status = "closed"
        elif auction.starts_at <= now:
            auction.status = "open"
        else:
            auction.status = "scheduled"

    await db.commit()
    logger.info("lifecycle: %s", stats)
    return stats


async def run_cleanup(db: AsyncSession) -> dict[str, int]:
    raw_days = await get_setting_int(db, "raw_retention_days", 30)
    closed_days = await get_setting_int(db, "closed_retention_days", 90)
    now = now_brt()
    res = await db.execute(delete(RawItem).where(RawItem.fetched_at < now - timedelta(days=raw_days)))
    removed_raw = res.rowcount or 0
    removed_items = 0
    if closed_days > 0:
        res = await db.execute(delete(Item).where(
            Item.status.in_(("closed", "withdrawn", "possibly_withdrawn")),
            Item.updated_at < now - timedelta(days=closed_days),
        ))
        removed_items = res.rowcount or 0
    await db.commit()
    logger.info("cleanup: %d raw, %d itens", removed_raw, removed_items)
    return {"raw_items": removed_raw, "items": removed_items}
