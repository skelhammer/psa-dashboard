"""FastAPI application: create app, include routers, startup/shutdown."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import get_database
from app.phone.factory import get_phone_provider
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
    logger.info("Starting PSA Dashboard")
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

    # Create phone provider if configured
    phone_provider = get_phone_provider(settings)
    app.state.phone_provider = phone_provider
    if phone_provider:
        logger.info("Phone provider: %s", phone_provider.get_provider_name())
        from app.sync.phone_engine import PhoneSyncEngine
        phone_engine = PhoneSyncEngine(
            phone_provider, db, settings.phone_sync.lookback_days
        )
        app.state.phone_engine = phone_engine
        # Run initial phone sync
        import asyncio
        asyncio.create_task(_phone_sync_loop(
            phone_engine, settings.phone_sync.interval_minutes
        ))
    else:
        app.state.phone_engine = None
        logger.info("Phone provider: none (disabled)")

    yield

    # Shutdown
    await scheduler.stop()
    await db.close()
    logger.info("Shutdown complete")


async def _phone_sync_loop(engine, interval_minutes: int):
    """Background loop for phone data sync."""
    try:
        logger.info("Running initial phone sync...")
        result = await engine.sync()
        logger.info("Initial phone sync: %s", result)
    except Exception as e:
        logger.error("Initial phone sync failed: %s", e)

    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)
            result = await engine.sync()
            logger.info("Scheduled phone sync: %s", result)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Phone sync failed: %s", e)


def create_app() -> FastAPI:
    app = FastAPI(
        title="PSA Dashboard",
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
    from app.api.routes_clients import router as client_router
    from app.api.routes_executive import router as executive_router
    from app.api.routes_phone import router as phone_router
    from app.api.routes_alerts import router as alerts_router

    app.include_router(sync_router)
    app.include_router(filters_router)
    app.include_router(mtz_router)
    app.include_router(queue_router)
    app.include_router(overview_router)
    app.include_router(tech_router)
    app.include_router(billing_router)
    app.include_router(client_router)
    app.include_router(executive_router)
    app.include_router(phone_router)
    app.include_router(alerts_router)

    return app
