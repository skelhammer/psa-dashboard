"""Sync and health API routes."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["sync"])

# Manual sync debounce: reject repeated trigger requests within this window.
# Protects PSA/phone APIs from being hammered if a user click-spams the
# Sync button. The scheduler still runs on its normal interval regardless.
MANUAL_SYNC_MIN_INTERVAL_SECONDS = 60
MANUAL_FULL_SYNC_MIN_INTERVAL_SECONDS = 300

# Module-level state: timestamp of the last manual trigger of each kind.
_last_manual_trigger: dict[str, datetime] = {}


def _check_debounce(kind: str, min_interval: int) -> None:
    """Raise 429 if a manual sync of this kind was triggered too recently."""
    last = _last_manual_trigger.get(kind)
    now = datetime.now()
    if last and (now - last) < timedelta(seconds=min_interval):
        retry_after = int(min_interval - (now - last).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Manual {kind} sync was triggered recently; retry in {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )
    _last_manual_trigger[kind] = now


async def _get_last_sync(request: Request) -> str | None:
    """Return last sync time, falling back to sync_log if in-memory value is None."""
    scheduler = request.app.state.scheduler
    if scheduler.last_sync_time:
        return scheduler.last_sync_time.isoformat()
    # Fall back to most recent completed sync in the database
    db = request.app.state.db
    conn = await db.get_connection()
    rows = await conn.execute_fetchall(
        "SELECT completed_at FROM sync_log WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"
    )
    if rows:
        return rows[0][0]
    return None


@router.get("/health")
async def health(request: Request):
    scheduler = request.app.state.scheduler
    providers = request.app.state.providers
    return {
        "status": "ok",
        "providers": list(providers.keys()),
        "syncing": scheduler.is_syncing,
        "last_sync": await _get_last_sync(request),
    }


@router.post("/sync/trigger")
async def trigger_sync(request: Request):
    scheduler = request.app.state.scheduler
    if scheduler.is_syncing:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    _check_debounce("incremental", MANUAL_SYNC_MIN_INTERVAL_SECONDS)
    result = await scheduler.trigger_sync()
    return result


@router.post("/sync/full")
async def trigger_full_sync(request: Request):
    """Trigger a full sync that re-fetches all tickets and removes deleted ones."""
    scheduler = request.app.state.scheduler
    if scheduler.is_syncing:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    _check_debounce("full", MANUAL_FULL_SYNC_MIN_INTERVAL_SECONDS)
    result = await scheduler.trigger_full_sync()
    return result


@router.get("/sync/status")
async def sync_status(request: Request):
    scheduler = request.app.state.scheduler
    providers = request.app.state.providers
    db = request.app.state.db

    conn = await db.get_connection()
    rows = await conn.execute_fetchall(
        "SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 10"
    )

    recent_syncs = []
    for row in rows:
        recent_syncs.append({
            "id": row["id"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "tickets_synced": row["tickets_synced"],
            "errors": row["errors"],
            "provider_name": row["provider_name"],
        })

    # Per-provider sync status
    provider_status = {}
    manager = request.app.state.manager
    for name, engine in manager.engines.items():
        provider_status[name] = {
            "is_syncing": engine.is_syncing,
            "last_sync": engine.last_sync_time.isoformat() if engine.last_sync_time else None,
        }

    return {
        "is_syncing": scheduler.is_syncing,
        "last_sync": await _get_last_sync(request),
        "providers": list(providers.keys()),
        "provider_status": provider_status,
        "recent_syncs": recent_syncs,
    }
