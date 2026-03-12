"""Technician Performance API."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL, OPEN_STATUSES_SQL, PRIORITY_ORDER, ticket_row_to_dict

router = APIRouter(prefix="/api", tags=["technicians"])


@router.get("/technicians")
async def technicians_list(request: Request, filters: FilterParams = Depends()):
    """Get performance metrics for all technicians."""
    db = request.app.state.db
    conn = await db.get_connection()

    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    stale_days_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'stale_ticket_threshold_days'"
    )
    stale_days = int(stale_days_row[0][0]) if stale_days_row else 3
    stale_cutoff = (now - timedelta(days=stale_days)).isoformat()

    techs = await conn.execute_fetchall(
        "SELECT id, first_name, last_name, email, role, available_hours_per_week FROM technicians"
    )

    result = []
    for tech in techs:
        tech_id = tech["id"]
        tech_name = f"{tech['first_name']} {tech['last_name']}".strip()

        # Open tickets
        open_count = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL}",
            (tech_id,),
        )

        # Closed this week / this month
        closed_week = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?",
            (tech_id, week_start.isoformat()),
        )
        closed_month = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?",
            (tech_id, month_start.isoformat()),
        )

        # Avg first response time (this month, minutes)
        avg_fr = await conn.execute_fetchall(
            """SELECT AVG((julianday(first_response_time) - julianday(created_time)) * 24 * 60)
               FROM tickets WHERE technician_id = ? AND first_response_time IS NOT NULL AND created_time >= ?""",
            (tech_id, month_start.isoformat()),
        )

        # Avg resolution time (this month, minutes)
        avg_res = await conn.execute_fetchall(
            """SELECT AVG((julianday(resolution_time) - julianday(created_time)) * 24 * 60)
               FROM tickets WHERE technician_id = ? AND resolution_time IS NOT NULL AND created_time >= ?""",
            (tech_id, month_start.isoformat()),
        )

        # SLA violations
        fr_violations = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND first_response_violated = 1 AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )
        res_violations = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND resolution_violated = 1 AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )

        # Total tickets this month (for SLA violation %)
        total_month = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )

        # FCR
        fcr_eligible = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )
        fcr_count = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
                WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND created_time >= ?
                AND tech_reply_count = 1
                AND (julianday(resolution_time) - julianday(created_time)) * 24 <= 4""",
            (tech_id, month_start.isoformat()),
        )

        fcr_total = fcr_eligible[0][0] or 0
        fcr_rate = round((fcr_count[0][0] / fcr_total * 100) if fcr_total > 0 else 0, 1)

        # Worklog hours this month
        worklog = await conn.execute_fetchall(
            "SELECT SUM(worklog_minutes) FROM tickets WHERE technician_id = ? AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )
        worklog_hours = round((worklog[0][0] or 0) / 60, 1)

        # Utilization (worklog hours / available hours for the period)
        available_per_week = tech["available_hours_per_week"] or 40
        weeks_in_period = max((now - month_start).days / 7, 1)
        available_hours = available_per_week * weeks_in_period
        utilization = round((worklog_hours / available_hours * 100) if available_hours > 0 else 0, 1)

        # Stale tickets
        stale = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL} AND updated_time < ?",
            (tech_id, stale_cutoff),
        )

        # Reopened
        reopened = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND reopened = 1 AND created_time >= ?",
            (tech_id, month_start.isoformat()),
        )

        # Billing compliance (% of hourly-client tickets with worklog)
        billable_tickets = await conn.execute_fetchall(
            """SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.technician_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed') AND t.created_time >= ?""",
            (tech_id, month_start.isoformat()),
        )
        billed_tickets = await conn.execute_fetchall(
            """SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.technician_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed') AND t.created_time >= ?
               AND t.worklog_minutes > 0""",
            (tech_id, month_start.isoformat()),
        )
        billable_total = billable_tickets[0][0] or 0
        billing_compliance = round((billed_tickets[0][0] / billable_total * 100) if billable_total > 0 else 100, 1)

        total_m = total_month[0][0] or 0

        result.append({
            "id": tech_id,
            "name": tech_name,
            "email": tech["email"],
            "role": tech["role"],
            "open_tickets": open_count[0][0],
            "closed_this_week": closed_week[0][0],
            "closed_this_month": closed_month[0][0],
            "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
            "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
            "fcr_rate_pct": fcr_rate,
            "fr_violations": fr_violations[0][0],
            "fr_violation_pct": round((fr_violations[0][0] / total_m * 100) if total_m > 0 else 0, 1),
            "res_violations": res_violations[0][0],
            "res_violation_pct": round((res_violations[0][0] / total_m * 100) if total_m > 0 else 0, 1),
            "worklog_hours": worklog_hours,
            "utilization_pct": utilization,
            "stale_tickets": stale[0][0],
            "reopened_tickets": reopened[0][0],
            "billing_compliance_pct": billing_compliance,
        })

    return {"technicians": result}


@router.get("/technicians/{tech_id}")
async def technician_detail(tech_id: str, request: Request, filters: FilterParams = Depends()):
    """Get detailed view for a specific technician."""
    db = request.app.state.db
    conn = await db.get_connection()

    # Tech info
    tech_rows = await conn.execute_fetchall(
        "SELECT * FROM technicians WHERE id = ?", (tech_id,)
    )
    if not tech_rows:
        return {"error": "Technician not found"}

    tech = tech_rows[0]

    # Open tickets
    open_tickets = await conn.execute_fetchall(
        f"""SELECT * FROM tickets
            WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL}
            ORDER BY {PRIORITY_ORDER} DESC, first_response_due ASC""",
        (tech_id,),
    )

    # Category breakdown
    categories = await conn.execute_fetchall(
        """SELECT category, COUNT(*) as count FROM tickets
           WHERE technician_id = ? AND category IS NOT NULL
           GROUP BY category ORDER BY count DESC""",
        (tech_id,),
    )

    # Client breakdown
    clients = await conn.execute_fetchall(
        """SELECT client_name, COUNT(*) as count FROM tickets
           WHERE technician_id = ?
           GROUP BY client_name ORDER BY count DESC""",
        (tech_id,),
    )

    provider = request.app.state.provider
    tickets = [ticket_row_to_dict(row) for row in open_tickets]
    for t in tickets:
        t["url"] = provider.get_ticket_url(t["id"])

    return {
        "technician": {
            "id": tech["id"],
            "name": f"{tech['first_name']} {tech['last_name']}".strip(),
            "email": tech["email"],
            "role": tech["role"],
        },
        "open_tickets": tickets,
        "categories": [{"category": r["category"], "count": r["count"]} for r in categories],
        "clients": [{"client": r["client_name"], "count": r["count"]} for r in clients],
    }
