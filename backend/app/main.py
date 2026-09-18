import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_current_user
from app.config import get_settings
from app.database import init_db
from app.v1 import categories, items, portal, settings_routes, sources
from app.v1.auth_routes import router as auth_router
from app.v1.branding import admin_router as branding_admin_router, public_router as branding_public_router
from app.v1.operations import dashboard_router, duplicates_router, incidents_router, jobs_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("zleilao")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ZConnect Leilão...")
    await init_db()
    from app.database import AsyncSessionLocal
    from app.seed import seed_admin_user, seed_categories, seed_sources
    from app.settings_service import seed_defaults

    async with AsyncSessionLocal() as db:
        await seed_defaults(db)
        await seed_admin_user(db)
        await seed_categories(db)
        await seed_sources(db)
    if settings.SCHEDULER_ENABLED:
        from app.scheduler.jobs import start_scheduler
        await start_scheduler()
    else:
        logger.info("Scheduler desabilitado (SCHEDULER_ENABLED=false)")
    logger.info("Application ready.")
    yield
    from app.scheduler.jobs import shutdown_scheduler
    shutdown_scheduler()
    logger.info("Shutdown complete.")


app = FastAPI(title="ZConnect Leilão", version="0.1.0", lifespan=lifespan, redirect_slashes=False)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Publico ────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/v1", tags=["Auth"])
app.include_router(portal.router, prefix="/v1", tags=["Portal"])
app.include_router(branding_public_router, prefix="/v1", tags=["Branding"])

# ── Admin (JWT) ────────────────────────────────────────────────────
auth = [Depends(get_current_user)]
app.include_router(dashboard_router, prefix="/v1", tags=["Dashboard"], dependencies=auth)
app.include_router(sources.router, prefix="/v1/sources", tags=["Sources"], dependencies=auth)
app.include_router(categories.router, prefix="/v1/categories", tags=["Categories"], dependencies=auth)
app.include_router(items.router, prefix="/v1/items", tags=["Items"], dependencies=auth)
app.include_router(incidents_router, prefix="/v1/incidents", tags=["Incidents"], dependencies=auth)
app.include_router(jobs_router, prefix="/v1/jobs", tags=["Jobs"], dependencies=auth)
app.include_router(duplicates_router, prefix="/v1/duplicates", tags=["Duplicates"], dependencies=auth)
app.include_router(settings_routes.router, prefix="/v1/settings", tags=["Settings"], dependencies=auth)
app.include_router(branding_admin_router, prefix="/v1", tags=["Branding"], dependencies=auth)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "zconnect-leilao"}
