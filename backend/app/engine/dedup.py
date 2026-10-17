"""RN-004 — deduplicacao entre fontes.

Dois patamares. Acima de `threshold` nasce um vinculo `suspected`, que o
admin confirma ou rejeita. Acima de `merge_threshold` o vinculo ja' nasce
`confirmed` (F4, "deduplicacao plena"): a vitrine mostra um lote so', com as
fontes onde ele aparece, e o espelho some da listagem enquanto o canonico
estiver visivel.

**Por que a fusao automatica exige evidencia forte.** Leilao de frota vende
cinquenta Onix 2022 brancos, mesma UF, km parecido: titulo, ano, km, UF e cor
batem e sao carros diferentes. So' placa igual (hash) ou a mesma URL oficial
(portal que republica o lote do leiloeiro) distinguem "o mesmo carro" de "um
carro igual". Por isso a pontuacao por semelhanca nunca chega a 1.0, e o
padrao de `merge_threshold` e' 1.0 — so' evidencia forte funde. Baixar o
limiar e' escolha do admin, com esse risco.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app.models import Item, ItemDuplicate

logger = logging.getLogger("zleilao.dedup")

ACTIVE = ("published", "auction_soon", "collected")

#: Placa igual ou URL oficial igual: e' o mesmo bem, nao um parecido.
STRONG = 1.0
#: Teto da semelhanca sem evidencia forte: nunca empata com STRONG.
SIMILARITY_CAP = 0.99


def _tokens(s: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", unidecode(s or "").lower()) if len(t) > 1}


def _url_key(u: str | None) -> str | None:
    """Host sem www + caminho sem barra final. Query e fragmento ficam de fora:
    portais costumam anexar rastreio a um link que e' o mesmo lote."""
    if not u:
        return None
    s = urlsplit(u.strip().lower())
    host = s.netloc[4:] if s.netloc.startswith("www.") else s.netloc
    path = s.path.rstrip("/")
    return f"{host}{path}" if host and path else None


def is_strong(reasons: dict) -> bool:
    return reasons.get("placa") == 1.0 or reasons.get("url") == 1.0


def similarity(a: Item, b: Item) -> tuple[float, dict]:
    reasons: dict[str, float] = {}
    if a.plate_hash and b.plate_hash:
        if a.plate_hash == b.plate_hash:
            reasons["placa"] = 1.0
            return STRONG, reasons
        # Placas conhecidas e diferentes: sao carros diferentes, por mais que
        # o resto bata. Sem esta regra a frota vira um emaranhado de suspeitos.
        reasons["placa"] = 0.0
        return 0.0, reasons
    ua, ub = _url_key(a.official_url), _url_key(b.official_url)
    if ua and ub and ua == ub:
        reasons["url"] = 1.0
        return STRONG, reasons

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
    return round(min(score, SIMILARITY_CAP), 3), reasons


async def run_dedup(db: AsyncSession, threshold: float, merge_threshold: float = 1.0) -> tuple[int, int]:
    """Devolve (vinculos criados, dos quais fundidos automaticamente)."""
    rows = (await db.execute(select(Item).where(Item.status.in_(ACTIVE), Item.extraction_status == "done"))).scalars().all()
    existing = {(d.canonical_item_id, d.duplicate_item_id) for d in (await db.execute(select(ItemDuplicate))).scalars().all()}
    existing |= {(b, a) for a, b in existing}

    groups: dict[tuple, list[Item]] = defaultdict(list)
    for it in rows:
        if it.plate_hash:
            groups[("plate", it.plate_hash)].append(it)
        url = _url_key(it.official_url)
        if url:
            groups[("url", url)].append(it)
        if it.brand and it.model and it.year_model:
            groups[("bmy", it.brand.lower(), it.model.lower(), it.year_model)].append(it)

    created = 0
    merged = 0
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
                if sim < threshold:
                    continue
                # O canonico e' a publicacao mais antiga: e' a que o usuario ja'
                # pode ter visto, salvo ou recebido por alerta.
                canonical, dup = (a, b) if a.first_seen_at <= b.first_seen_at else (b, a)
                funde = sim >= merge_threshold
                if funde:
                    reasons["auto"] = True
                    merged += 1
                db.add(ItemDuplicate(canonical_item_id=canonical.id, duplicate_item_id=dup.id,
                                     similarity=sim, reasons=reasons,
                                     status="confirmed" if funde else "suspected"))
                seen_pairs.add(pair)
                created += 1
    if created:
        await db.commit()
    logger.info("dedup: %d novos vinculos (%d fundidos; limiares %.2f / %.2f)", created, merged, threshold, merge_threshold)
    return created, merged
