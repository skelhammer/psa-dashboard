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
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else now.isoformat()

    # Build extra filter conditions from client/priority
    extra_and = ""
    extra_params: list = []
    if filters.client_id:
        extra_and += " AND client_id = ?"
        extra_params.append(filters.client_id)
    if filters.priority:
        extra_and += " AND priority = ?"
        extra_params.append(filters.priority)
    if filters.tech_group:
        extra_and += " AND COALESCE(tech_group_name, 'Tier 1 Support') = ?"
        extra_params.append(filters.tech_group)

    # For joined queries (t. prefix)
    extra_and_t = extra_and.replace("client_id", "t.client_id").replace("priority", "t.priority").replace("tech_group_name", "t.tech_group_name")

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

        # Open tickets (not date-filtered, always current)
        open_count = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL}{extra_and}",
            [tech_id, *extra_params],
        )

        # Closed in period (by resolution_time)
        closed_period = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )

        # Avg first response time (tickets created in period, business minutes)
        avg_fr = await conn.execute_fetchall(
            f"""SELECT AVG(first_response_business_minutes)
               FROM tickets WHERE technician_id = ? AND first_response_business_minutes > 0 AND created_time >= ? AND created_time <= ?{extra_and}""",
            [tech_id, period_start, period_end, *extra_params],
        )

        # Avg resolution time (tickets resolved in period, business minutes)
        avg_res = await conn.execute_fetchall(
            f"""SELECT AVG(resolution_business_minutes)
               FROM tickets WHERE technician_id = ? AND resolution_business_minutes > 0 AND resolution_time >= ? AND resolution_time <= ?{extra_and}""",
            [tech_id, period_start, period_end, *extra_params],
        )

        # SLA violations (tickets created in period)
        fr_violations = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND first_response_violated = 1 AND created_time >= ? AND created_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )
        res_violations = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND resolution_violated = 1 AND created_time >= ? AND created_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )

        # Total tickets in period (for SLA violation %)
        total_period = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND created_time >= ? AND created_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )

        # Worklog hours (tickets resolved in period)
        worklog = await conn.execute_fetchall(
            f"SELECT SUM(worklog_minutes) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )
        worklog_hours = round((worklog[0][0] or 0) / 60, 1)

        # Utilization (worklog hours / available hours for the period)
        available_per_week = tech["available_hours_per_week"] or 40
        period_days = max((filters.date_to - filters.date_from).days, 1) if filters.date_to else max((now - filters.date_from).days, 1)
        weeks_in_period = max(period_days / 7, 1)
        available_hours = available_per_week * weeks_in_period
        utilization = round((worklog_hours / available_hours * 100) if available_hours > 0 else 0, 1)

        # Stale tickets (always current, not date-filtered)
        stale = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL} AND updated_time < ?{extra_and}",
            [tech_id, stale_cutoff, *extra_params],
        )

        # Reopened (in period)
        reopened = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND reopened = 1 AND updated_time >= ? AND updated_time <= ?{extra_and}",
            [tech_id, period_start, period_end, *extra_params],
        )

        # Billing compliance (% of hourly-client tickets with worklog, resolved in period)
        billable_tickets = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.technician_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed') AND t.resolution_time >= ? AND t.resolution_time <= ?{extra_and_t}""",
            [tech_id, period_start, period_end, *extra_params],
        )
        billed_tickets = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.technician_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed') AND t.resolution_time >= ? AND t.resolution_time <= ?
               AND t.worklog_minutes > 0{extra_and_t}""",
            [tech_id, period_start, period_end, *extra_params],
        )
        billable_total = billable_tickets[0][0] or 0
        billing_compliance = round((billed_tickets[0][0] / billable_total * 100) if billable_total > 0 else 100, 1)

        total_p = total_period[0][0] or 0

        result.append({
            "id": tech_id,
            "name": tech_name,
            "email": tech["email"],
            "role": tech["role"],
            "open_tickets": open_count[0][0],
            "closed_period": closed_period[0][0],
            "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
            "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
            "fr_violations": fr_violations[0][0],
            "fr_violation_pct": round((fr_violations[0][0] / total_p * 100) if total_p > 0 else 0, 1),
            "res_violations": res_violations[0][0],
            "res_violation_pct": round((res_violations[0][0] / total_p * 100) if total_p > 0 else 0, 1),
            "worklog_hours": worklog_hours,
            "utilization_pct": utilization,
            "stale_tickets": stale[0][0],
            "reopened_tickets": reopened[0][0],
            "billing_compliance_pct": billing_compliance,
        })

    return {"technicians": result, "date_range_label": filters.date_range_label}


@router.get("/technicians/{tech_id}")
async def technician_detail(tech_id: str, request: Request, filters: FilterParams = Depends()):
    """Get detailed view for a specific technician."""
    db = request.app.state.db
    conn = await db.get_connection()

    now = datetime.now()
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else now.isoformat()

    # Build extra filter conditions
    extra_and = ""
    extra_params: list = []
    if filters.client_id:
        extra_and += " AND client_id = ?"
        extra_params.append(filters.client_id)
    if filters.priority:
        extra_and += " AND priority = ?"
        extra_params.append(filters.priority)
    if filters.tech_group:
        extra_and += " AND COALESCE(tech_group_name, 'Tier 1 Support') = ?"
        extra_params.append(filters.tech_group)

    # Stale threshold
    stale_days_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'stale_ticket_threshold_days'"
    )
    stale_days = int(stale_days_row[0][0]) if stale_days_row else 3
    stale_cutoff = (now - timedelta(days=stale_days)).isoformat()

    # Tech info
    tech_rows = await conn.execute_fetchall(
        "SELECT * FROM technicians WHERE id = ?", (tech_id,)
    )
    if not tech_rows:
        return {"error": "Technician not found"}

    tech = tech_rows[0]

    # --- KPI queries ---

    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL}{extra_and}",
        [tech_id, *extra_params],
    )

    closed_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )

    avg_fr = await conn.execute_fetchall(
        f"""SELECT AVG(first_response_business_minutes)
           FROM tickets WHERE technician_id = ? AND first_response_business_minutes > 0
           AND created_time >= ? AND created_time <= ?{extra_and}""",
        [tech_id, period_start, period_end, *extra_params],
    )

    avg_res = await conn.execute_fetchall(
        f"""SELECT AVG(resolution_business_minutes)
           FROM tickets WHERE technician_id = ? AND resolution_business_minutes > 0
           AND resolution_time >= ? AND resolution_time <= ?{extra_and}""",
        [tech_id, period_start, period_end, *extra_params],
    )

    fr_violations = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND first_response_violated = 1 AND created_time >= ? AND created_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )

    res_violations = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND resolution_violated = 1 AND created_time >= ? AND created_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )

    total_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND created_time >= ? AND created_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )

    worklog = await conn.execute_fetchall(
        f"SELECT SUM(worklog_minutes) FROM tickets WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )
    worklog_hours = round((worklog[0][0] or 0) / 60, 1)

    available_per_week = tech["available_hours_per_week"] or 40
    period_days = max((filters.date_to - filters.date_from).days, 1) if filters.date_to else max((now - filters.date_from).days, 1)
    weeks_in_period = max(period_days / 7, 1)
    available_hours = available_per_week * weeks_in_period
    utilization = round((worklog_hours / available_hours * 100) if available_hours > 0 else 0, 1)

    stale = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL} AND updated_time < ?{extra_and}",
        [tech_id, stale_cutoff, *extra_params],
    )

    reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND reopened = 1 AND updated_time >= ? AND updated_time <= ?{extra_and}",
        [tech_id, period_start, period_end, *extra_params],
    )

    total_p = total_period[0][0] or 0
    fr_viol = fr_violations[0][0]
    res_viol = res_violations[0][0]
    fr_viol_pct = round((fr_viol / total_p * 100) if total_p > 0 else 0, 1)
    res_viol_pct = round((res_viol / total_p * 100) if total_p > 0 else 0, 1)

    kpis = {
        "open_tickets": open_count[0][0],
        "closed_period": closed_period[0][0],
        "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
        "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
        "fr_violations": fr_viol,
        "fr_violation_pct": fr_viol_pct,
        "res_violations": res_viol,
        "res_violation_pct": res_viol_pct,
        "worklog_hours": worklog_hours,
        "utilization_pct": utilization,
        "stale_tickets": stale[0][0],
        "reopened_tickets": reopened[0][0],
        "sla_compliance_pct": round(max(100 - fr_viol_pct - res_viol_pct, 0), 1),
    }

    # --- Volume trend (last 12 weeks) ---
    twelve_weeks_ago = (now - timedelta(weeks=12)).isoformat()
    volume_trend = await conn.execute_fetchall(
        f"""SELECT
                strftime('%Y-%m-%d', date(created_time, 'weekday 0', '-6 days')) AS week,
                COUNT(*) AS created,
                SUM(CASE WHEN status IN {CLOSED_STATUSES_SQL} THEN 1 ELSE 0 END) AS closed
            FROM tickets
            WHERE technician_id = ? AND created_time >= ?{extra_and}
            GROUP BY week ORDER BY week""",
        [tech_id, twelve_weeks_ago, *extra_params],
    )

    # --- SLA trend (last 12 weeks) ---
    sla_trend = await conn.execute_fetchall(
        f"""SELECT
                strftime('%Y-%m-%d', date(created_time, 'weekday 0', '-6 days')) AS week,
                COUNT(*) AS total,
                SUM(CASE WHEN first_response_violated = 1 OR resolution_violated = 1 THEN 1 ELSE 0 END) AS violated
            FROM tickets
            WHERE technician_id = ? AND created_time >= ?{extra_and}
            GROUP BY week ORDER BY week""",
        [tech_id, twelve_weeks_ago, *extra_params],
    )

    # --- Categories (period only) ---
    categories = await conn.execute_fetchall(
        f"""SELECT category, COUNT(*) as count FROM tickets
           WHERE technician_id = ? AND category IS NOT NULL
           AND created_time >= ? AND created_time <= ?{extra_and}
           GROUP BY category ORDER BY count DESC""",
        [tech_id, period_start, period_end, *extra_params],
    )

    # --- Clients (period only) ---
    clients = await conn.execute_fetchall(
        f"""SELECT client_name, COUNT(*) as count FROM tickets
           WHERE technician_id = ?
           AND created_time >= ? AND created_time <= ?{extra_and}
           GROUP BY client_name ORDER BY count DESC""",
        [tech_id, period_start, period_end, *extra_params],
    )

    # --- Recent closed tickets ---
    recent_closed_rows = await conn.execute_fetchall(
        f"""SELECT * FROM tickets
            WHERE technician_id = ? AND status IN {CLOSED_STATUSES_SQL}
            AND resolution_time >= ? AND resolution_time <= ?{extra_and}
            ORDER BY resolution_time DESC LIMIT 10""",
        [tech_id, period_start, period_end, *extra_params],
    )

    # --- Open tickets ---
    open_tickets = await conn.execute_fetchall(
        f"""SELECT * FROM tickets
            WHERE technician_id = ? AND status IN {OPEN_STATUSES_SQL}{extra_and}
            ORDER BY {PRIORITY_ORDER} DESC, first_response_due ASC""",
        [tech_id, *extra_params],
    )

    provider = request.app.state.provider

    open_list = [ticket_row_to_dict(row) for row in open_tickets]
    for t in open_list:
        t["url"] = provider.get_ticket_url(t["id"])

    closed_list = [ticket_row_to_dict(row) for row in recent_closed_rows]
    for t in closed_list:
        t["url"] = provider.get_ticket_url(t["id"])

    return {
        "technician": {
            "id": tech["id"],
            "name": f"{tech['first_name']} {tech['last_name']}".strip(),
            "email": tech["email"],
            "role": tech["role"],
        },
        "kpis": kpis,
        "volume_trend": [
            {"week": r["week"], "created": r["created"], "closed": r["closed"]}
            for r in volume_trend
        ],
        "categories": [{"category": r["category"], "count": r["count"]} for r in categories],
        "clients": [{"client": r["client_name"], "count": r["count"]} for r in clients],
        "sla_trend": [
            {
                "week": r["week"],
                "compliance_pct": round(
                    ((r["total"] - r["violated"]) / r["total"] * 100) if r["total"] > 0 else 100, 1
                ),
            }
            for r in sla_trend
        ],
        "recent_closed": closed_list,
        "open_tickets": open_list,
        "date_range_label": filters.date_range_label,
    }
