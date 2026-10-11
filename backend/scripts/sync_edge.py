#!/usr/bin/env python
"""Envia para a Cloudflare os lotes que mudaram desde a ultima sincronizacao.

Por que o Postgres local continua no meio do caminho, em vez de o coletor
falar direto com o D1: o pipeline que ja' existe faz muito mais que coletar.
Ele normaliza, classifica categoria, decide ciclo de vida (RN-005), deduplica
entre fontes (RN-004) e calcula o score de oportunidade (RN-010) — tudo com
estado que exige varias passadas sobre a base. Mantendo esse trabalho aqui, a
borda so' recebe o resultado pronto, e nada daquilo precisou ser reescrito.

O Postgres tambem serve de amortecedor: se a Cloudflare estiver fora do ar, a
coleta continua e a sincronizacao se resolve na proxima rodada.

Uso:
    python scripts/sync_edge.py --url https://zleilao-api.workers.dev --token XYZ
    python scripts/sync_edge.py --full          # reenvia tudo, ignora o marcador
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Auction, Category, Item, Source  # noqa: E402
from app.timeutil import now_brt  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zleilao.sync")

#: Quantos lotes por requisicao. Pequeno o bastante para a requisicao nao
#: estourar limite de corpo, grande o bastante para nao virar conversa fiada.
PAGINA = 40

#: Onde fica o marcador do ultimo envio. Fora do banco de proposito: e' estado
#: desta maquina, nao do sistema.
MARCADOR = Path(__file__).resolve().parent / ".sync_edge.json"


def _decimal(v) -> float | None:
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else v


def _dt(v) -> str | None:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v else None


def ler_marcador() -> str | None:
    if not MARCADOR.exists():
        return None
    try:
        return json.loads(MARCADOR.read_text(encoding="utf-8")).get("desde")
    except (OSError, ValueError):
        return None


def gravar_marcador(quando: str) -> None:
    MARCADOR.write_text(json.dumps({"desde": quando}, ensure_ascii=False), encoding="utf-8")


async def montar_lote(db, itens: list[Item], cats: dict[int, str], pregoes: dict[int, Auction]) -> list[dict]:
    """Converte os itens do ORM para o formato que a rota de ingestao espera."""
    saida = []
    for i in itens:
        pregao = pregoes.get(i.auction_id) if i.auction_id else None
        corpo = {
            "external_id": i.external_id,
            "title": i.title,
            "official_url": i.official_url,
            "item_type": i.item_type,
            "description": i.description,
            "lot_number": i.lot_number,
            "price": _decimal(i.price),
            "price_kind": i.price_kind,
            "price_second": _decimal(i.price_second),
            "city": i.city,
            "state": i.state,
            "location_text": i.location_text,
            "lat": i.lat,
            "lng": i.lng,
            "image_url": i.image_url,
            "images": i.images or [],
            # `_raw` e `_category_hint` sao andaimes da extracao: nao vao para
            # a vitrine, e carregam texto bruto que so' engorda a requisicao.
            "attributes": {k: v for k, v in (i.attributes or {}).items() if not k.startswith("_")},
            "brand": i.brand,
            "model": i.model,
            "year_model": i.year_model,
            "year_fab": i.year_fab,
            "km": i.km,
            "condition": i.condition,
            "status": i.status,
            "status_hint": i.status_hint,
            "content_hash": i.content_hash,
            "next_session_at": _dt(i.next_session_at),
            "category_slug": cats.get(i.category_id) if i.category_id else None,
        }
        if pregao:
            corpo["auction"] = {
                "external_id": pregao.external_id,
                "title": pregao.title,
                "auctioneer_name": pregao.auctioneer_name,
                "auctioneer_registration": pregao.auctioneer_registration,
                "committer_name": pregao.committer_name,
                "modality": pregao.modality,
                "auction_type": pregao.auction_type,
                "official_url": pregao.official_url,
                "status": pregao.status,
                "starts_at": _dt(pregao.starts_at),
                "ends_at": _dt(pregao.ends_at),
                "sessions": [
                    {
                        "kind": s.kind,
                        "sequence": s.sequence,
                        "starts_at": _dt(s.starts_at),
                        "ends_at": _dt(s.ends_at),
                        "min_bid": _decimal(s.min_bid),
                    }
                    for s in sorted(pregao.sessions, key=lambda x: x.sequence)
                ],
            }
        saida.append(corpo)
    return saida


async def sincronizar(url: str, token: str, completo: bool, limite: int | None) -> int:
    desde = None if completo else ler_marcador()
    inicio = now_brt().strftime("%Y-%m-%d %H:%M:%S")

    async with AsyncSessionLocal() as db:
        cats = {c.id: c.slug for c in (await db.execute(select(Category))).scalars().all()}
        fontes = {s.id: s.slug for s in (await db.execute(select(Source))).scalars().all()}

        consulta = select(Item).order_by(Item.source_id, Item.id)
        if desde:
            consulta = consulta.where(Item.updated_at >= text("'%s'" % desde))
        if limite:
            consulta = consulta.limit(limite)
        itens = (await db.execute(consulta)).scalars().unique().all()

        if not itens:
            logger.info("nada mudou desde %s", desde or "sempre")
            gravar_marcador(inicio)
            return 0

        ids_pregao = {i.auction_id for i in itens if i.auction_id}
        pregoes = {}
        if ids_pregao:
            from sqlalchemy.orm import selectinload

            rows = (await db.execute(
                select(Auction).where(Auction.id.in_(ids_pregao)).options(selectinload(Auction.sessions))
            )).scalars().unique().all()
            pregoes = {a.id: a for a in rows}

        # Uma requisicao por fonte e por pagina: a rota de ingestao recebe o
        # slug da fonte no corpo, e misturar fontes numa chamada so' tornaria
        # o erro mais dificil de ler.
        por_fonte: dict[int, list[Item]] = {}
        for i in itens:
            por_fonte.setdefault(i.source_id, []).append(i)

        enviados = 0
        async with httpx.AsyncClient(timeout=60) as http:
            for source_id, lista in por_fonte.items():
                slug = fontes.get(source_id)
                if not slug:
                    continue
                for ini in range(0, len(lista), PAGINA):
                    fatia = lista[ini : ini + PAGINA]
                    corpo = {
                        "source_slug": slug,
                        "complete": completo,
                        "items": await montar_lote(db, fatia, cats, pregoes),
                    }
                    r = await http.post(
                        f"{url.rstrip('/')}/ingest/batch",
                        json=corpo,
                        headers={"x-ingest-token": token},
                    )
                    if r.status_code != 200:
                        logger.error("falha ao enviar %s [%s]: %s", slug, r.status_code, r.text[:200])
                        # Nao grava o marcador: a proxima rodada tenta de novo.
                        return enviados
                    res = r.json()
                    enviados += res.get("inseridos", 0) + res.get("atualizados", 0)
                    logger.info(
                        "%s: %d enviados (%d novos, %d atualizados, %d ignorados)",
                        slug, res.get("recebidos", 0), res.get("inseridos", 0),
                        res.get("atualizados", 0), res.get("ignorados", 0),
                    )
                    for e in res.get("erros", []):
                        logger.warning("  %s", e)

    gravar_marcador(inicio)
    return enviados


def main() -> int:
    p = argparse.ArgumentParser(description="Sincroniza os lotes locais com a API na Cloudflare")
    p.add_argument("--url", default=os.getenv("EDGE_URL", ""), help="URL do Worker")
    p.add_argument("--token", default=os.getenv("EDGE_TOKEN", ""), help="token de ingestão")
    p.add_argument("--full", action="store_true", help="reenvia tudo, ignorando o marcador")
    p.add_argument("--limit", type=int, default=None, help="envia no máximo N lotes (teste)")
    a = p.parse_args()

    if not a.url or not a.token:
        p.error("informe --url e --token (ou as variáveis EDGE_URL e EDGE_TOKEN)")

    total = asyncio.run(sincronizar(a.url, a.token, a.full, a.limit))
    logger.info("sincronização concluída: %d lotes", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
