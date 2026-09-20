"""Job do comparador: busca a referência FIPE dos bens publicados e calcula o
score de oportunidade (RN-010).

Trabalha por *bem* (marca/modelo/ano), não por lote: dezenas de lotes de
"Fiat Uno 2010" consultam a FIPE uma única vez. A referência vale 30 dias por
padrão — a tabela muda uma vez por mês.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.deterministic import has_damage_words
from app.engine.fipe import FipeClient, FipeUnavailable, vehicle_type_for
from app.engine.lifecycle import VISIBLE_STATUSES
from app.engine.opportunity import UNKNOWN_CONDITIONS, compute, presume_condition
from app.models import Category, Item, ItemOpportunity, PriceReference
from app.settings_service import get_setting, get_setting_bool, get_setting_float, get_setting_int
from app.timeutil import now_brt

logger = logging.getLogger("zleilao.comparator")


async def _reference_for(
    db: AsyncSession, client: FipeClient, *, vehicle: str, brand: str, model: str,
    year: int, fuel: str | None, ttl_days: int,
) -> PriceReference | None:
    """Referência em cache ou consultada na FIPE."""
    existing = await db.scalar(select(PriceReference).where(
        PriceReference.vehicle_type == vehicle, PriceReference.brand == brand,
        PriceReference.model == model, PriceReference.year == year,
        PriceReference.fuel == fuel, PriceReference.source_kind == "fipe",
    ))
    if existing and existing.computed_at >= now_brt() - timedelta(days=ttl_days):
        return existing

    match = await client.lookup(vehicle=vehicle, brand=brand, model=model, year=year, fuel_hint=fuel)
    if not match:
        return existing  # mantém a referência velha se a consulta não casar

    if existing:
        existing.value = match.value
        existing.fipe_code = match.fipe_code
        existing.fipe_model_label = match.model_label
        existing.reference_month = match.reference_month
        existing.match_ratio = match.ratio
        existing.computed_at = now_brt()
        return existing

    ref = PriceReference(
        vehicle_type=vehicle, brand=brand, model=model, year=year, fuel=fuel,
        source_kind="fipe", value=match.value, sample_size=1,
        fipe_code=match.fipe_code, fipe_model_label=match.model_label,
        reference_month=match.reference_month, match_ratio=match.ratio,
    )
    db.add(ref)
    await db.flush()
    return ref


async def run_comparator(db: AsyncSession) -> dict[str, Any]:
    ttl_days = await get_setting_int(db, "price_reference_ttl_days", 30)
    max_lookups = await get_setting_int(db, "fipe_max_lookups_per_cycle", 40)
    commission = await get_setting_float(db, "default_commission_pct", 5.0)
    base_url = await get_setting(db, "fipe_api_url", "https://parallelum.com.br/fipe/api/v1")
    presume_enabled = await get_setting_bool(db, "comparator_presume_condition", True)
    stats = {"items": 0, "scored": 0, "presumed": 0, "no_reference": 0, "no_condition": 0,
             "lookups": 0, "stopped": None}

    categories = {c.id: c for c in (await db.execute(select(Category))).scalars().all()}
    items = (await db.execute(
        select(Item).where(
            Item.status.in_(VISIBLE_STATUSES), Item.item_type == "lot",
            Item.brand.isnot(None), Item.model.isnot(None), Item.year_model.isnot(None),
            Item.price.isnot(None),
        )
    )).scalars().all()

    # Agrupa por bem: a FIPE é consultada uma vez por (marca, modelo, ano).
    groups: dict[tuple, list[Item]] = {}
    for it in items:
        cat = categories.get(it.category_id)
        vehicle = vehicle_type_for(cat.path if cat else None)
        if not vehicle:
            continue
        fuel = (it.attributes or {}).get("combustivel")
        groups.setdefault((vehicle, it.brand, it.model, it.year_model, fuel), []).append(it)

    async with FipeClient(base_url) as client:
        for (vehicle, brand, model, year, fuel), members in groups.items():
            if stats["lookups"] >= max_lookups:
                stats["stopped"] = f"limite de {max_lookups} consultas por ciclo"
                break
            try:
                ref = await _reference_for(db, client, vehicle=vehicle, brand=brand, model=model,
                                           year=year, fuel=fuel, ttl_days=ttl_days)
            except FipeUnavailable as exc:
                stats["stopped"] = str(exc)
                logger.warning("comparador interrompido: %s", exc)
                break
            stats["lookups"] += 1

            for it in members:
                stats["items"] += 1
                if not ref:
                    stats["no_reference"] += 1
                    continue
                attrs = it.attributes or {}
                presumed = None
                if it.condition in UNKNOWN_CONDITIONS and presume_enabled:
                    text = " ".join(str(x) for x in (it.title, it.description, attrs.get("observacoes")) if x)
                    presumed = presume_condition(attrs.get("origem"), has_damage_words(text))
                result = compute(
                    price=it.price, reference_value=ref.value, condition=it.condition,
                    raw_attributes=attrs.get("_raw"), default_commission=commission,
                    presumed_condition=presumed, price_kind=it.price_kind,
                )
                if not result:
                    stats["no_condition"] += 1
                    continue
                opp = await db.scalar(select(ItemOpportunity).where(ItemOpportunity.item_id == it.id))
                if not opp:
                    opp = ItemOpportunity(item_id=it.id)
                    db.add(opp)
                opp.price_reference_id = ref.id
                opp.reference_value = ref.value
                opp.total_cost = result["total_cost"]
                opp.discount_pct = result["discount_pct"]
                opp.score = result["score"]
                opp.reasons = result["reasons"]
                opp.computed_at = now_brt()
                stats["scored"] += 1
                if result["reasons"].get("condicao_presumida"):
                    stats["presumed"] += 1

    # Lote que saiu da vitrine não deve manter score pendurado.
    visible_ids = {i.id for i in items}
    stale = (await db.execute(select(ItemOpportunity))).scalars().all()
    removed = 0
    for opp in stale:
        if opp.item_id not in visible_ids:
            await db.delete(opp)
            removed += 1
    stats["removed"] = removed

    await db.commit()
    logger.info("comparador: %s", stats)
    return stats
