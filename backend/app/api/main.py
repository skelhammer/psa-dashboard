"""FastAPI application: create app, include routers, startup/shutdown."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth.ratelimit import LoginRateLimiter
from app.auth.session import load_or_create_signing_key
from app.config import get_settings
from app.database import get_database
from app.phone.factory import get_phone_provider
from app.psa.factory import get_providers
from app.sync.engine import SyncEngine
from app.sync.manager import MultiProviderSyncManager
from app.sync.scheduler import SyncScheduler
from app.vault import crypto
from app.vault.manager import SecretsManager
from app.vault.migrate import migrate_from_yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _bootstrap_kek(settings) -> bytes:
    """Load the master key, preferring the env var if set, else the key file.

    The env var path is the advanced deployment mode (key off disk). The
    file path is the default and auto-generates on first run.
    """
    env_var = settings.vault.env_var_override
    if env_var and os.environ.get(env_var, "").strip():
        logger.info("vault: loading master key from environment variable %s", env_var)
        return crypto.load_kek_from_env(env_var)
    key_path = Path(settings.vault.key_file)
    return crypto.load_or_create_kek_file(key_path)


def _resolve_yaml_path() -> Path:
    """Mirror the lookup in app.config.load_settings so the migration finds
    the same file the loader did."""
    candidate = Path(os.environ.get("CONFIG_PATH", "config.yaml"))
    if candidate.exists():
        return candidate
    root = Path(__file__).resolve().parents[3]
    return root / "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, bootstrap vault, migrate yaml, build providers, start scheduler."""
    settings = get_settings()
    logger.info("Starting PSA Dashboard")

    # Initialize database
    db = get_database(settings.db_path)
    await db.initialize()
    app.state.db = db

    # Bootstrap vault: load (or create) master key, then construct manager.
    kek = _bootstrap_kek(settings)
    vault = SecretsManager(db, kek)
    app.state.vault = vault

    # Initialize the in-memory login rate limiter (per-process state).
    app.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=settings.auth.login_max_attempts,
        window_seconds=settings.auth.login_window_minutes * 60,
    )

    # One-time migration from plaintext config.yaml. Idempotent on re-runs.
    yaml_path = _resolve_yaml_path()
    migration = await migrate_from_yaml(yaml_path, vault)
    if migration.migrated:
        logger.info(
            "vault: migrated %d secret(s) from %s into the encrypted store",
            len(migration.migrated),
            yaml_path,
        )
    if migration.backup_written:
        logger.warning(
            "vault: original plaintext yaml backed up at %s. "
            "MOVE OR DELETE this file once you have verified the dashboard works.",
            migration.backup_written,
        )

    # Create all configured PSA providers (now async, vault-aware)
    providers_list = await get_providers(settings, vault)
    provider_map = {p.get_provider_name().lower(): p for p in providers_list}
    logger.info("PSA providers: %s", ", ".join(provider_map.keys()))

    app.state.providers = provider_map
    app.state.provider = providers_list[0]  # Backward compat

    # Create sync engines (one per provider) and manager
    engines = {name: SyncEngine(p, db) for name, p in provider_map.items()}
    manager = MultiProviderSyncManager(engines)
    scheduler = SyncScheduler(manager, settings.sync.interval_minutes)
    app.state.scheduler = scheduler
    app.state.manager = manager
    await scheduler.start()

    # Create phone provider if configured (now async, vault-aware)
    phone_provider = await get_phone_provider(settings, vault)
    app.state.phone_provider = phone_provider
    if phone_provider:
        logger.info("Phone provider: %s", phone_provider.get_provider_name())
        from app.sync.phone_engine import PhoneSyncEngine
        phone_engine = PhoneSyncEngine(
            phone_provider, db, settings.phone_sync.lookback_days
        )
        app.state.phone_engine = phone_engine
        app.state.phone_task = asyncio.create_task(_phone_sync_loop(
            phone_engine, settings.phone_sync.interval_minutes
        ))
    else:
        app.state.phone_engine = None
        app.state.phone_task = None
        logger.info("Phone provider: none (disabled)")

    yield

    # Shutdown
    await scheduler.stop()
    if getattr(app.state, "phone_task", None):
        app.state.phone_task.cancel()
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

    settings = get_settings()
    signing_key = load_or_create_signing_key(settings.session_signing_key_path)
    app.add_middleware(
        SessionMiddleware,
        secret_key=signing_key,
        session_cookie="psa_dashboard_session",
        max_age=settings.auth.session_ttl_minutes * 60,
        same_site="lax",
        https_only=False,
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
    from app.api.routes_contracts import router as contracts_router
    from app.api.routes_auth import router as auth_router
    from app.api.routes_admin_secrets import router as admin_secrets_router

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
    app.include_router(contracts_router)
    app.include_router(auth_router)
    app.include_router(admin_secrets_router)

    return app
