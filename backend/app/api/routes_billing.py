"""Billing Audit API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.dependencies import FilterParams
from app.api.queries import PRIORITY_ORDER, get_closed_statuses_sql, get_ticket_url, ticket_row_to_dict

router = APIRouter(prefix="/api/billing", tags=["billing"])


class ResolveFlag(BaseModel):
    resolved_by: str
    resolution_note: str


@router.get("/flags")
async def billing_flags(
    request: Request,
    filters: FilterParams = Depends(),
    resolved: bool = Query(False, description="Show resolved flags"),
    flag_type: str | None = Query(None),
):
    """Get billing flags with filters."""
    db = request.app.state.db
    conn = await db.get_connection()

    conditions = ["bf.resolved = ?"]
    params: list = [1 if resolved else 0]

    # Date filter on resolution_time (when the ticket was closed)
    if filters.date_from:
        conditions.append("t.resolution_time >= ?")
        params.append(filters.date_from.isoformat())
    if filters.date_to:
        conditions.append("t.resolution_time <= ?")
        params.append(filters.date_to.isoformat())

    if flag_type:
        conditions.append("bf.flag_type = ?")
        params.append(flag_type)
    if filters.client_id:
        conditions.append("t.client_id = ?")
        params.append(filters.client_id)
    if filters.technician_id:
        conditions.append("t.technician_id = ?")
        params.append(filters.technician_id)
    if filters.priority:
        conditions.append("t.priority = ?")
        params.append(filters.priority)
    if filters.tech_group:
        conditions.append("COALESCE(t.tech_group_name, 'Tier 1 Support') = ?")
        params.append(filters.tech_group)
    if filters.provider:
        conditions.append("t.provider = ?")
        params.append(filters.provider)
    if filters.hide_corp:
        conditions.append("t.is_corp = 0")

    where = " AND ".join(conditions)

    rows = await conn.execute_fetchall(
        f"""SELECT bf.*, t.display_id, t.subject, t.client_id, t.client_name,
               t.technician_id, t.technician_name, t.status, t.priority,
               t.created_time, t.worklog_hours
           FROM billing_flags bf
           JOIN tickets t ON bf.ticket_id = t.id
           WHERE {where}
           ORDER BY {PRIORITY_ORDER} DESC, bf.flagged_at DESC""",
        params,
    )

    providers = request.app.state.providers
    flags = []
    for row in rows:
        flags.append({
            "id": row["id"],
            "ticket_id": row["ticket_id"],
            "display_id": row["display_id"],
            "subject": row["subject"],
            "client_name": row["client_name"],
            "technician_name": row["technician_name"],
            "status": row["status"],
            "priority": row["priority"],
            "flag_type": row["flag_type"],
            "flag_reason": row["flag_reason"],
            "flagged_at": row["flagged_at"],
            "resolved": bool(row["resolved"]),
            "resolved_by": row["resolved_by"],
            "resolved_at": row["resolved_at"],
            "resolution_note": row["resolution_note"],
            "worklog_hours": row["worklog_hours"],
            "created_time": row["created_time"],
            "url": get_ticket_url(row["ticket_id"], providers),
        })

    return {"flags": flags, "count": len(flags), "date_range_label": filters.date_range_label}


@router.patch("/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: int, body: ResolveFlag, request: Request):
    """Mark a billing flag as resolved."""
    db = request.app.state.db
    conn = await db.get_connection()
    now = datetime.now().isoformat()

    await conn.execute(
        """UPDATE billing_flags
           SET resolved = 1, resolved_by = ?, resolved_at = ?, resolution_note = ?
           WHERE id = ?""",
        (body.resolved_by, now, body.resolution_note, flag_id),
    )
    await conn.commit()
    return {"status": "resolved", "flag_id": flag_id}


@router.get("/summary")
async def billing_summary(request: Request, filters: FilterParams = Depends()):
    """KPI cards and client billing summary."""
    db = request.app.state.db
    conn = await db.get_connection()

    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else None

    date_cond = "t.resolution_time >= ?"
    date_params: list = [period_start]
    if period_end:
        date_cond += " AND t.resolution_time <= ?"
        date_params.append(period_end)

    # Unresolved flags (tickets closed in period)
    unresolved = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM billing_flags bf
           JOIN tickets t ON bf.ticket_id = t.id
           WHERE bf.resolved = 0 AND {date_cond}""",
        date_params,
    )

    # Flags resolved in period
    resolved_params: list = [period_start]
    resolved_cond = "resolved_at >= ?"
    if period_end:
        resolved_cond += " AND resolved_at <= ?"
        resolved_params.append(period_end)
    resolved_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM billing_flags WHERE resolved = 1 AND {resolved_cond}",
        resolved_params,
    )

    # Billable client summary
    clients = await conn.execute_fetchall(
        """SELECT bc.client_id, c.name, bc.billing_type, bc.hourly_rate,
               bc.auto_detected, bc.track_billing
           FROM billing_config bc
           JOIN clients c ON bc.client_id = c.id
           WHERE bc.track_billing = 1 AND c.stage = 'Active'
           ORDER BY c.name"""
    )

    client_summaries = []
    for client in clients:
        cid = client["client_id"]

        client_date_cond = "resolution_time >= ?"
        client_date_params: list = [period_start]
        if period_end:
            client_date_cond += " AND resolution_time <= ?"
            client_date_params.append(period_end)

        # Exclude tickets that have a resolved billing flag (already addressed)
        resolved_flag_exclude = """AND id NOT IN (
            SELECT ticket_id FROM billing_flags WHERE resolved = 1 AND flag_type = 'MISSING_WORKLOG'
        )"""
        closed_sql = get_closed_statuses_sql()
        total = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN {closed_sql} AND {client_date_cond} {resolved_flag_exclude}",
            [cid, *client_date_params],
        )
        with_time = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN {closed_sql} AND {client_date_cond} AND worklog_hours > 0 {resolved_flag_exclude}",
            [cid, *client_date_params],
        )
        hours = await conn.execute_fetchall(
            f"SELECT SUM(worklog_hours) FROM tickets WHERE client_id = ? AND status IN {closed_sql} AND {client_date_cond}",
            [cid, *client_date_params],
        )
        flags = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM billing_flags bf
               JOIN tickets t ON bf.ticket_id = t.id
               WHERE t.client_id = ? AND bf.resolved = 0 AND {date_cond}""",
            [cid, *client_date_params],
        )

        total_count = total[0][0] or 0
        with_time_count = with_time[0][0] or 0
        missing = total_count - with_time_count

        client_summaries.append({
            "client_id": cid,
            "name": client["name"],
            "billing_type": client["billing_type"],
            "hourly_rate": client["hourly_rate"],
            "auto_detected": bool(client["auto_detected"]),
            "total_tickets": total_count,
            "tickets_with_time": with_time_count,
            "tickets_missing_time": missing,
            "missing_pct": round((missing / total_count * 100) if total_count > 0 else 0, 1),
            "billed_hours": round(hours[0][0] or 0, 1),
            "unresolved_flags": flags[0][0],
        })

    return {
        "kpis": {
            "unresolved_flags": unresolved[0][0],
            "resolved_period": resolved_period[0][0],
        },
        "clients": client_summaries,
        "date_range_label": filters.date_range_label,
    }
