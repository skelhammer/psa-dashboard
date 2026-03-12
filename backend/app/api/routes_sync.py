"""Sync and health API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["sync"])


@router.get("/health")
async def health(request: Request):
    scheduler = request.app.state.scheduler
    return {
        "status": "ok",
        "provider": request.app.state.provider.get_provider_name(),
        "syncing": scheduler.engine.is_syncing,
        "last_sync": scheduler.engine.last_sync_time.isoformat() if scheduler.engine.last_sync_time else None,
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
        "last_sync": scheduler.engine.last_sync_time.isoformat() if scheduler.engine.last_sync_time else None,
        "provider": request.app.state.provider.get_provider_name(),
        "recent_syncs": recent_syncs,
    }
