"""RN-004 — deduplicacao conservadora entre fontes.

Nunca funde: cria vinculos `suspected` que o admin confirma/rejeita. Placa
igual (hash) e' evidencia forte; sem placa, usa marca/modelo/ano + titulo +
km + UF.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.models import Item, ItemDuplicate

logger = logging.getLogger("zleilao.dedup")

ACTIVE = ("published", "auction_soon", "collected")


def _tokens(s: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", unidecode(s or "").lower()) if len(t) > 1}


def similarity(a: Item, b: Item) -> tuple[float, dict]:
    reasons: dict[str, float] = {}
    if a.plate_hash and b.plate_hash and a.plate_hash == b.plate_hash:
        reasons["placa"] = 1.0
        return 1.0, reasons
    score = 0.0
    ta, tb = _tokens(a.title), _tokens(b.title)
    if ta and tb:
        j = len(ta & tb) / len(ta | tb)
        score += 0.4 * j
        reasons["titulo"] = round(j, 2)
    if a.year_model and b.year_model:
        if a.year_model == b.year_model:
            score += 0.2
            reasons["ano"] = 1.0
        elif abs(a.year_model - b.year_model) == 1:
            score += 0.1
            reasons["ano"] = 0.5
    if a.km and b.km:
        diff = abs(a.km - b.km) / max(a.km, b.km)
        if diff <= 0.1:
            score += 0.15
            reasons["km"] = 1.0
    elif not a.km and not b.km:
        score += 0.05
    if a.state and b.state and a.state == b.state:
        score += 0.15
        reasons["uf"] = 1.0
    ca, cb = (a.attributes or {}).get("cor"), (b.attributes or {}).get("cor")
    if ca and cb and unidecode(str(ca)).lower() == unidecode(str(cb)).lower():
        score += 0.1
        reasons["cor"] = 1.0
    return round(min(score, 1.0), 3), reasons


async def run_dedup(db: AsyncSession, threshold: float) -> int:
    rows = (await db.execute(select(Item).where(Item.status.in_(ACTIVE), Item.extraction_status == "done"))).scalars().all()
    existing = {(d.canonical_item_id, d.duplicate_item_id) for d in (await db.execute(select(ItemDuplicate))).scalars().all()}
    existing |= {(b, a) for a, b in existing}

    groups: dict[tuple, list[Item]] = defaultdict(list)
    for it in rows:
        if it.plate_hash:
            groups[("plate", it.plate_hash)].append(it)
        if it.brand and it.model and it.year_model:
            groups[("bmy", it.brand.lower(), it.model.lower(), it.year_model)].append(it)

    created = 0
    seen_pairs: set[tuple[int, int]] = set()
    for key, members in groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a.source_id == b.source_id:
                    continue  # mesma fonte: chave natural ja' evita duplicidade
                pair = (min(a.id, b.id), max(a.id, b.id))
                if pair in existing or pair in seen_pairs:
                    continue
                sim, reasons = similarity(a, b)
                if sim >= threshold:
                    canonical, dup = (a, b) if a.first_seen_at <= b.first_seen_at else (b, a)
                    db.add(ItemDuplicate(canonical_item_id=canonical.id, duplicate_item_id=dup.id,
                                         similarity=sim, reasons=reasons, status="suspected"))
                    seen_pairs.add(pair)
                    created += 1
    if created:
        await db.commit()
    logger.info("dedup: %d novos vinculos suspeitos (limiar %.2f)", created, threshold)
    return created
