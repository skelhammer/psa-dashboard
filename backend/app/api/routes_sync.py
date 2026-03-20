"""Sync and health API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["sync"])


async def _get_last_sync(request: Request) -> str | None:
    """Return last sync time, falling back to sync_log if in-memory value is None (e.g. after restart)."""
    engine = request.app.state.scheduler.engine
    if engine.last_sync_time:
        return engine.last_sync_time.isoformat()
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
    return {
        "status": "ok",
        "provider": request.app.state.provider.get_provider_name(),
        "syncing": scheduler.engine.is_syncing,
        "last_sync": await _get_last_sync(request),
    }


@router.post("/sync/trigger")
async def trigger_sync(request: Request):
    scheduler = request.app.state.scheduler
    result = await scheduler.trigger_sync()
    return result


@router.post("/sync/full")
async def trigger_full_sync(request: Request):
    """Trigger a full sync that re-fetches all tickets and removes deleted ones."""
    scheduler = request.app.state.scheduler
    result = await scheduler.trigger_full_sync()
    return result


@router.get("/sync/status")
async def sync_status(request: Request):
    scheduler = request.app.state.scheduler
    db = request.app.state.db

    conn = await db.get_connection()
    rows = await conn.execute_fetchall(
        "SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 5"
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

    return {
        "is_syncing": scheduler.engine.is_syncing,
        "last_sync": await _get_last_sync(request),
        "provider": request.app.state.provider.get_provider_name(),
        "recent_syncs": recent_syncs,
    }
