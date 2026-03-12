"""FastAPI application: create app, include routers, startup/shutdown."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import get_database
from app.psa.factory import get_provider
from app.sync.engine import SyncEngine
from app.sync.scheduler import SyncScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, create provider, start sync scheduler."""
    settings = get_settings()
    logger.info("Starting Integotec Manager Dashboard")
    logger.info("PSA provider: %s", settings.psa.provider)

    # Initialize database
    db = get_database(settings.db_path)
    await db.initialize()
    app.state.db = db

    # Create provider
    provider = get_provider(settings)
    app.state.provider = provider

    # Create and start sync scheduler
    engine = SyncEngine(provider, db)
    scheduler = SyncScheduler(engine, settings.sync.interval_minutes)
    app.state.scheduler = scheduler
    await scheduler.start()

    yield

    # Shutdown
    await scheduler.stop()
    await db.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Integotec Manager Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from app.api.routes_sync import router as sync_router
    from app.api.routes_filters import router as filters_router
    from app.api.routes_mtz import router as mtz_router
    from app.api.routes_queue import router as queue_router
    from app.api.routes_overview import router as overview_router
    from app.api.routes_technicians import router as tech_router
    from app.api.routes_billing import router as billing_router

    app.include_router(sync_router)
    app.include_router(filters_router)
    app.include_router(mtz_router)
    app.include_router(queue_router)
    app.include_router(overview_router)
    app.include_router(tech_router)
    app.include_router(billing_router)

    return app
