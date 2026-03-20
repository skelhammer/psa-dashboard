"""Alerts API: active alerts and CEO summary."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.alerts.engine import compute_health_summary, generate_insights

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts/active")
async def active_alerts(request: Request):
    """Get currently active insight-based alerts."""
    db = request.app.state.db
    conn = await db.get_connection()
    insights = await generate_insights(conn)
    return {"alerts": insights}


@router.get("/executive/summary")
async def executive_summary(request: Request):
    """CEO summary: overall health indicator + natural language + insights."""
    db = request.app.state.db
    conn = await db.get_connection()
    health = await compute_health_summary(conn)
    insights = await generate_insights(conn)
    return {
        "health": health,
        "insights": insights[:3],
    }
