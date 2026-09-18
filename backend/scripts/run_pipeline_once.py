"""Roda o pipeline inteiro uma vez, fora do scheduler. Util para desenvolvimento,
primeira carga e diagnostico.

    cd backend
    DATABASE_URL=postgresql+asyncpg://zleilao:zleilaopass@localhost:5434/zleilao \
    SCHEDULER_ENABLED=false .venv/Scripts/python scripts/run_pipeline_once.py \
        --sources megaleiloes,freitas,leilo --max-pages 1 --details 3

Sem --sources, coleta todas as fontes ativas com a config cadastrada.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SCHEDULER_ENABLED", "false")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal, init_db
    from app.models import Source
    from app.scheduler.jobs import dedup_job, lifecycle_job, normalize_job, run_scrape_job
    from app.seed import seed_admin_user, seed_categories, seed_sources
    from app.settings_service import seed_defaults

    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_defaults(db)
        await seed_admin_user(db)
        await seed_categories(db)
        await seed_sources(db)

    wanted = [s.strip() for s in args.sources.split(",")] if args.sources else None
    results: dict[str, object] = {}
    async with AsyncSessionLocal() as db:
        sources = (await db.execute(select(Source).where(Source.is_active.is_(True)))).scalars().all()
        for s in sources:
            if wanted and s.slug not in wanted:
                continue
            if args.max_pages or args.details is not None:
                cfg = dict(s.config or {})
                if args.max_pages:
                    cfg["max_pages"] = args.max_pages
                    cfg["max_auctions"] = args.max_pages  # Leilo
                if args.details is not None:
                    cfg["fetch_details"] = args.details > 0
                    cfg["max_details_per_run"] = args.details
                s.config = cfg
                await db.commit()
            logging.info("=== coleta: %s ===", s.name)
            results[s.slug] = await run_scrape_job(db, s.id)

    if not args.skip_normalize:
        logging.info("=== normalize ===")
        results["normalize"] = await normalize_job()
    logging.info("=== lifecycle ===")
    results["lifecycle"] = await lifecycle_job()
    logging.info("=== dedup ===")
    results["dedup"] = await dedup_job()
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default="", help="slugs separados por virgula (default: todas ativas)")
    p.add_argument("--max-pages", type=int, default=0, help="limita paginas por fonte nesta execucao")
    p.add_argument("--details", type=int, default=None, help="max paginas de detalhe (0 = nenhuma)")
    p.add_argument("--skip-normalize", action="store_true")
    asyncio.run(main(p.parse_args()))
