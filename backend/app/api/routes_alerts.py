"""Alerts API: active alerts and CEO summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.alerts.engine import compute_health_summary, generate_insights
from app.api.dependencies import FilterParams

router = APIRouter(prefix="/api", tags=["alerts"])


def _build_health_filter_sql(filters: FilterParams) -> tuple[str, list]:
    """Build AND-able filter conditions for health summary (no date, no WHERE)."""
    conditions: list[str] = []
    params: list = []

    if filters.provider:
        conditions.append("provider = ?")
        params.append(filters.provider)
    if filters.hide_corp:
        conditions.append("is_corp = 0")
    if filters.client_id:
        conditions.append("client_id = ?")
        params.append(filters.client_id)
    if filters.technician_id:
        conditions.append("technician_id = ?")
        params.append(filters.technician_id)
    if filters.priority:
        conditions.append("priority = ?")
        params.append(filters.priority)
    if filters.category:
        conditions.append("category = ?")
        params.append(filters.category)
    if filters.tech_group:
        conditions.append("COALESCE(tech_group_name, 'Tier 1 Support') = ?")
        params.append(filters.tech_group)

    return " AND ".join(conditions), params


@router.get("/alerts/active")
async def active_alerts(request: Request):
    """Get currently active insight-based alerts."""
    db = request.app.state.db
    conn = await db.get_connection()
    insights = await generate_insights(conn)
    return {"alerts": insights}


@router.get("/executive/summary")
async def executive_summary(request: Request, filters: FilterParams = Depends()):
    """CEO summary: overall health indicator + natural language + insights."""
    db = request.app.state.db
    conn = await db.get_connection()
    extra_sql, extra_params = _build_health_filter_sql(filters)
    health = await compute_health_summary(conn, extra_sql, extra_params)
    insights = await generate_insights(conn)
    return {
        "health": health,
        "insights": insights[:3],
    }
