"""Billing Audit API."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.api.queries import PRIORITY_ORDER, ticket_row_to_dict

router = APIRouter(prefix="/api/billing", tags=["billing"])


class ResolveFlag(BaseModel):
    resolved_by: str
    resolution_note: str


@router.get("/flags")
async def billing_flags(
    request: Request,
    resolved: bool = Query(False, description="Show resolved flags"),
    flag_type: str | None = Query(None),
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
):
    """Get billing flags with filters."""
    db = request.app.state.db
    conn = await db.get_connection()

    conditions = ["bf.resolved = ?"]
    params: list = [1 if resolved else 0]

    if flag_type:
        conditions.append("bf.flag_type = ?")
        params.append(flag_type)
    if client_id:
        conditions.append("t.client_id = ?")
        params.append(client_id)
    if technician_id:
        conditions.append("t.technician_id = ?")
        params.append(technician_id)

    where = " AND ".join(conditions)

    rows = await conn.execute_fetchall(
        f"""SELECT bf.*, t.display_id, t.subject, t.client_id, t.client_name,
               t.technician_id, t.technician_name, t.status, t.priority,
               t.created_time, t.worklog_minutes
           FROM billing_flags bf
           JOIN tickets t ON bf.ticket_id = t.id
           WHERE {where}
           ORDER BY {PRIORITY_ORDER} DESC, bf.flagged_at DESC""",
        params,
    )

    provider = request.app.state.provider
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
            "worklog_minutes": row["worklog_minutes"],
            "created_time": row["created_time"],
            "url": provider.get_ticket_url(row["ticket_id"]),
        })

    return {"flags": flags, "count": len(flags)}


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
async def billing_summary(request: Request):
    """KPI cards and client billing summary."""
    db = request.app.state.db
    conn = await db.get_connection()

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - __import__("datetime").timedelta(days=now.weekday())

    # Unresolved flags
    unresolved = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
    )

    # Flags resolved this week / month
    resolved_week = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 1 AND resolved_at >= ?",
        (week_start.isoformat(),),
    )
    resolved_month = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 1 AND resolved_at >= ?",
        (month_start.isoformat(),),
    )

    # Billable client summary
    clients = await conn.execute_fetchall(
        """SELECT bc.client_id, c.name, bc.billing_type, bc.hourly_rate,
               bc.auto_detected, bc.track_billing
           FROM billing_config bc
           JOIN clients c ON bc.client_id = c.id
           WHERE bc.track_billing = 1
           ORDER BY c.name"""
    )

    client_summaries = []
    for client in clients:
        cid = client["client_id"]

        total = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN ('Resolved', 'Closed') AND created_time >= ?",
            (cid, month_start.isoformat()),
        )
        with_time = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN ('Resolved', 'Closed') AND created_time >= ? AND worklog_minutes > 0",
            (cid, month_start.isoformat()),
        )
        hours = await conn.execute_fetchall(
            "SELECT SUM(worklog_minutes) FROM tickets WHERE client_id = ? AND created_time >= ?",
            (cid, month_start.isoformat()),
        )
        flags = await conn.execute_fetchall(
            """SELECT COUNT(*) FROM billing_flags bf
               JOIN tickets t ON bf.ticket_id = t.id
               WHERE t.client_id = ? AND bf.resolved = 0""",
            (cid,),
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
            "total_tickets_month": total_count,
            "tickets_with_time": with_time_count,
            "tickets_missing_time": missing,
            "missing_pct": round((missing / total_count * 100) if total_count > 0 else 0, 1),
            "billed_hours": round((hours[0][0] or 0) / 60, 1),
            "unresolved_flags": flags[0][0],
        })

    return {
        "kpis": {
            "unresolved_flags": unresolved[0][0],
            "resolved_this_week": resolved_week[0][0],
            "resolved_this_month": resolved_month[0][0],
        },
        "clients": client_summaries,
    }
