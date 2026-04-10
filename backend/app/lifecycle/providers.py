"""Hot reload of provider clients after a secret changes.

When the admin updates a credential through the Settings UI, the running
PSAProvider / PhoneProvider instances are still holding the OLD value (the
SuperOps client cached its Authorization header at construction time, the
Zoom provider holds an OAuth token, etc.). This module rebuilds the
affected provider in place so the next sync uses the new credential
without requiring a backend restart.

Strategy:
- For PSA providers: build a fresh provider via the factory, wrap it in a
  new SyncEngine, atomically swap it into app.state.manager.engines and
  app.state.providers. Any sync that is currently in flight finishes with
  the old engine (it holds a local reference), which is harmless: worst
  case the in-flight sync fails with an auth error and the next tick
  picks up the new credential.
- For the phone provider: the background loop in main.py holds a long
  lived reference to the engine, so we must cancel that task and start a
  new one. The cancel-and-restart dance is encapsulated here.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.config import get_settings
from app.phone.factory import get_phone_provider
from app.psa.factory import _create_provider
from app.sync.engine import SyncEngine

logger = logging.getLogger(__name__)


# Map vault key prefixes to the provider name they affect.
_PSA_PREFIX_TO_NAME = {
    "psa.superops.": "superops",
    "psa.zendesk.": "zendesk",
}
_PHONE_PREFIX = "phone.zoom."


def _provider_for_key(key: str) -> tuple[str, str | None]:
    """Return (kind, provider_name). kind is one of: 'psa', 'phone', 'unknown'."""
    for prefix, name in _PSA_PREFIX_TO_NAME.items():
        if key.startswith(prefix):
            return "psa", name
    if key.startswith(_PHONE_PREFIX):
        return "phone", "zoom"
    return "unknown", None


async def rebuild_for_key(app: FastAPI, key: str) -> dict:
    """Rebuild the provider affected by a vault key change.

    Returns a dict describing what was reloaded so the route can return it
    in the API response. Never raises on "key does not affect any provider";
    that case returns kind='unknown' so the caller can no-op cleanly.
    """
    kind, name = _provider_for_key(key)
    if kind == "unknown":
        logger.info("hot reload: key %s does not affect any active provider", key)
        return {"reloaded": False, "kind": "unknown"}

    settings = get_settings()
    vault = app.state.vault
    db = app.state.db

    if kind == "psa":
        return await _rebuild_psa(app, settings, vault, db, name)
    if kind == "phone":
        return await _rebuild_phone(app, settings, vault, db)

    return {"reloaded": False, "kind": kind}


async def _rebuild_psa(app, settings, vault, db, name: str) -> dict:
    """Swap a PSA provider in app.state in place."""
    manager = app.state.manager
    if name not in manager.engines:
        # Provider isn't currently active (e.g. you set a Zendesk token but
        # zendesk isn't in psa.providers). Nothing to hot-reload; the next
        # full restart will pick it up if you add it to providers list.
        logger.info(
            "hot reload: provider %s is not currently active; skipping rebuild",
            name,
        )
        return {"reloaded": False, "kind": "psa", "provider": name, "reason": "inactive"}

    new_provider = await _create_provider(name, settings, vault)
    new_engine = SyncEngine(new_provider, db)

    # Atomic swap. Any in-flight sync keeps the old engine via local ref.
    manager.engines[name] = new_engine
    app.state.providers[name] = new_provider
    if hasattr(app.state, "provider") and app.state.provider.get_provider_name().lower() == name:
        app.state.provider = new_provider

    logger.info("hot reload: rebuilt PSA provider %s", name)
    return {"reloaded": True, "kind": "psa", "provider": name}


async def _rebuild_phone(app, settings, vault, db) -> dict:
    """Cancel the phone sync loop and restart it with a fresh provider."""
    if settings.phone.provider.lower() != "zoom":
        logger.info("hot reload: phone provider is not zoom; skipping rebuild")
        return {"reloaded": False, "kind": "phone", "reason": "not zoom"}

    # Cancel the existing background loop, if any.
    old_task = getattr(app.state, "phone_task", None)
    if old_task and not old_task.done():
        old_task.cancel()
        try:
            await old_task
        except (asyncio.CancelledError, Exception):
            pass

    new_provider = await get_phone_provider(settings, vault)
    if new_provider is None:
        app.state.phone_provider = None
        app.state.phone_engine = None
        app.state.phone_task = None
        return {"reloaded": True, "kind": "phone", "provider": None}

    from app.sync.phone_engine import PhoneSyncEngine
    new_engine = PhoneSyncEngine(
        new_provider, db, settings.phone_sync.lookback_days
    )
    app.state.phone_provider = new_provider
    app.state.phone_engine = new_engine

    # Lazy import to avoid circular dependency with app.api.main.
    from app.api.main import _phone_sync_loop
    app.state.phone_task = asyncio.create_task(
        _phone_sync_loop(new_engine, settings.phone_sync.interval_minutes)
    )

    logger.info("hot reload: rebuilt phone provider (zoom)")
    return {"reloaded": True, "kind": "phone", "provider": "zoom"}
