"""RN-006 — casamento entre itens e filtros salvos.

Gera `alerts` pendentes. NÃO envia nada: quem envia é o dispatcher, que aplica
janela de silêncio, limite diário e o formato do plano (digest ou imediato).

Três motivos de alerta:
  new         — lote publicado depois do último check do filtro
  price_drop  — lance inicial caiu acima do limiar desde o último preço visto
  new_session — pregão ganhou uma sessão nova (ex.: 2ª praça marcada)

A não-repetição é garantida no banco por `(user_id, item_id, reason)`, não por
consulta prévia: dois filtros do mesmo usuário podem casar com o mesmo lote no
mesmo ciclo, e só um alerta deve sobrar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.search import apply_filters, base_query, category_path_for, normalize_criteria
from app.models import Alert, Item, ItemPriceHistory, SavedFilter, User
from app.settings_service import get_setting_float, get_setting_int
from app.timeutil import now_brt

logger = logging.getLogger("zleilao.matcher")


async def _insert_alerts(db: AsyncSession, rows: list[dict]) -> int:
    """Insere ignorando duplicados — a unicidade é a regra de não-repetição."""
    if not rows:
        return 0
    stmt = pg_insert(Alert).values(rows).on_conflict_do_nothing(
        index_elements=["user_id", "item_id", "reason"]
    ).returning(Alert.id)
    result = await db.execute(stmt)
    return len(result.scalars().all())


async def _price_drops(db: AsyncSession, since: datetime, min_pct: float) -> dict[int, tuple[datetime, str]]:
    """Itens cujo preço caiu acima do limiar desde `since`.

    Devolve {item_id: (quando a queda ficou visível, descrição)}. A data volta
    junto porque cada filtro só deve receber quedas posteriores ao seu próprio
    último check — senão criar um filtro traz um lote de quedas antigas que o
    usuário nunca pediu.
    """
    rows = (await db.execute(
        select(
            ItemPriceHistory.item_id,
            func.min(ItemPriceHistory.price),
            func.max(ItemPriceHistory.price),
            func.max(ItemPriceHistory.observed_at),
        )
        .where(ItemPriceHistory.observed_at >= since)
        .group_by(ItemPriceHistory.item_id)
        .having(func.count(ItemPriceHistory.id) > 1)
    )).all()
    out: dict[int, tuple[datetime, str]] = {}
    for item_id, lo, hi, last_at in rows:
        if not lo or not hi or hi <= 0:
            continue
        drop = (hi - lo) / hi * Decimal(100)
        if float(drop) >= min_pct:
            desc = f"lance caiu {float(drop):.0f}% (de R$ {hi:,.2f} para R$ {lo:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")
            out[item_id] = (last_at, desc)
    return out


async def run_matcher(db: AsyncSession) -> dict[str, int]:
    """Avalia todos os filtros ativos. Idempotente: pode rodar quantas vezes
    quiser que não duplica alerta."""
    now = now_brt()
    lookback_h = await get_setting_int(db, "match_lookback_hours", 48)
    drop_pct = await get_setting_float(db, "alert_price_drop_pct", 10.0)
    max_per_run = await get_setting_int(db, "match_max_items_per_filter", 50)
    stats = {"filters": 0, "new": 0, "price_drop": 0, "skipped_inactive": 0}

    filters = (await db.execute(
        select(SavedFilter, User)
        .join(User, User.id == SavedFilter.user_id)
        .where(SavedFilter.is_active.is_(True), User.is_active.is_(True))
    )).all()

    drops = await _price_drops(db, now - timedelta(hours=lookback_h), drop_pct)

    for sf, user in filters:
        # Um usuário sem canal utilizável não gera alerta: o e-mail precisa estar
        # verificado, senão o primeiro disparo vira reclamação de spam.
        has_email = user.email_opt_in and user.email_verified_at is not None
        has_wa = user.whatsapp_opt_in and bool(user.phone)
        if not (has_email or has_wa):
            stats["skipped_inactive"] += 1
            continue

        stats["filters"] += 1
        criteria = normalize_criteria(sf.criteria)
        cat_path = await category_path_for(db, criteria.get("category"))
        # Primeira avaliação olha para trás uma janela curta, não o acervo
        # inteiro: senão o usuário recebe centenas de alertas ao criar o filtro.
        since = sf.last_checked_at or (now - timedelta(hours=lookback_h))

        stmt = apply_filters(base_query(), criteria, category_path=cat_path)
        new_items = (await db.execute(
            stmt.where(Item.published_at.isnot(None), Item.published_at >= since)
            .order_by(Item.published_at.desc()).limit(max_per_run)
        )).scalars().unique().all()

        rows = [
            {"user_id": user.id, "item_id": it.id, "saved_filter_id": sf.id, "reason": "new",
             "status": "pending", "created_at": now}
            for it in new_items
        ]
        stats["new"] += await _insert_alerts(db, rows)

        # Só quedas posteriores ao último check DESTE filtro.
        recent_drops = {iid: desc for iid, (at, desc) in drops.items() if at >= since}
        if recent_drops:
            drop_items = (await db.execute(
                apply_filters(base_query(), criteria, category_path=cat_path)
                .where(Item.id.in_(list(recent_drops.keys()))).limit(max_per_run)
            )).scalars().unique().all()
            rows = [
                {"user_id": user.id, "item_id": it.id, "saved_filter_id": sf.id, "reason": "price_drop",
                 "status": "pending", "detail": recent_drops[it.id], "created_at": now}
                for it in drop_items
            ]
            stats["price_drop"] += await _insert_alerts(db, rows)

        sf.last_checked_at = now
        if new_items:
            sf.last_matched_at = now
            sf.matches_count = (sf.matches_count or 0) + len(new_items)

    await db.commit()
    logger.info("matcher: %s", stats)
    return stats
