"""Client Health API: per-client health scores, SLA compliance, and ticket metrics."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL, PRIORITY_ORDER, ticket_row_to_dict
from app.config import get_settings

router = APIRouter(prefix="/api", tags=["clients"])


def _now_tz() -> datetime:
    tz = ZoneInfo(get_settings().server.timezone)
    return datetime.now(tz)


def _build_filter_sql(filters: FilterParams, prefix: str = "") -> tuple[str, list]:
    """Build AND-able filter conditions from FilterParams (no WHERE keyword).

    Excludes client_id since client endpoints handle that separately.
    """
    conditions = []
    params = []
    col = f"{prefix}." if prefix else ""

    if filters.technician_id:
        conditions.append(f"{col}technician_id = ?")
        params.append(filters.technician_id)
    if filters.priority:
        conditions.append(f"{col}priority = ?")
        params.append(filters.priority)
    if filters.category:
        conditions.append(f"{col}category = ?")
        params.append(filters.category)
    if filters.tech_group:
        conditions.append(f"COALESCE({col}tech_group_name, 'Tier 1 Support') = ?")
        params.append(filters.tech_group)

    return " AND ".join(conditions), params


def _compute_health_score(
    sla_compliance_pct: float,
    avg_first_response_minutes: float,
    reopened_count: int,
    ticket_volume: int,
    billing_compliance_pct: float,
) -> int:
    """Compute weighted health score 0-100."""
    # SLA compliance: 40% weight
    sla_points = (sla_compliance_pct / 100) * 40

    # Response time: 25% weight (under 60min = full, over 480min = 0, linear)
    if avg_first_response_minutes <= 60:
        response_points = 25
    elif avg_first_response_minutes >= 480:
        response_points = 0
    else:
        response_points = 25 * (1 - (avg_first_response_minutes - 60) / (480 - 60))

    # Reopened rate: 15% weight (0% = full, >10% = 0)
    if ticket_volume > 0:
        reopened_rate = (reopened_count / ticket_volume) * 100
    else:
        reopened_rate = 0
    if reopened_rate <= 0:
        reopen_points = 15
    elif reopened_rate >= 10:
        reopen_points = 0
    else:
        reopen_points = 15 * (1 - reopened_rate / 10)

    # Billing compliance: 20% weight
    billing_points = (billing_compliance_pct / 100) * 20

    score = sla_points + response_points + reopen_points + billing_points
    return round(max(0, min(100, score)))


def _health_color(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


@router.get("/clients")
async def clients_list(request: Request, filters: FilterParams = Depends()):
    """Get health metrics for all active clients."""
    db = request.app.state.db
    conn = await db.get_connection()

    now = _now_tz()
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else now.isoformat()

    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # For joined queries (t. prefix)
    extra_and_t = extra_and.replace("technician_id", "t.technician_id").replace(
        "priority", "t.priority"
    ).replace("category", "t.category").replace("tech_group_name", "t.tech_group_name")

    # Get active clients
    clients = await conn.execute_fetchall(
        "SELECT id, name FROM clients WHERE stage = 'Active' ORDER BY name"
    )

    result = []
    for client in clients:
        client_id = client["id"]

        # Ticket volume (created in period)
        ticket_vol = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND created_time >= ? AND created_time <= ?{extra_and}",
            [client_id, period_start, period_end, *extra_params],
        )

        # Open tickets (current)
        open_count = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status NOT IN {CLOSED_STATUSES_SQL}{extra_and}",
            [client_id, *extra_params],
        )

        # Closed in period
        closed_period = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
            [client_id, period_start, period_end, *extra_params],
        )

        # SLA compliance
        total_with_sla = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time <= ?
               AND sla_name IS NOT NULL{extra_and}""",
            [client_id, period_start, period_end, *extra_params],
        )
        violated_sla = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time <= ?
               AND sla_name IS NOT NULL
               AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
            [client_id, period_start, period_end, *extra_params],
        )
        total_sla = total_with_sla[0][0] or 0
        violated = violated_sla[0][0] or 0
        sla_compliance = round(((total_sla - violated) / total_sla * 100) if total_sla > 0 else 100, 1)

        # Average first response time (business hours)
        avg_fr = await conn.execute_fetchall(
            f"""SELECT AVG(first_response_business_minutes) FROM tickets
            WHERE client_id = ? AND first_response_business_minutes > 0
            AND created_time >= ? AND created_time <= ?{extra_and}""",
            [client_id, period_start, period_end, *extra_params],
        )

        # Average resolution time (business hours)
        avg_res = await conn.execute_fetchall(
            f"""SELECT AVG(resolution_business_minutes) FROM tickets
            WHERE client_id = ? AND resolution_business_minutes > 0
            AND created_time >= ? AND created_time <= ?{extra_and}""",
            [client_id, period_start, period_end, *extra_params],
        )

        # Billed hours (closed tickets in period)
        worklog = await conn.execute_fetchall(
            f"""SELECT SUM(worklog_hours) FROM tickets
               WHERE client_id = ? AND status IN {CLOSED_STATUSES_SQL}
               AND resolution_time >= ? AND resolution_time <= ?{extra_and}""",
            [client_id, period_start, period_end, *extra_params],
        )
        billed_hours = round(worklog[0][0] or 0, 1)

        # Reopened count
        reopened = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND reopened = 1 AND updated_time >= ? AND updated_time <= ?{extra_and}",
            [client_id, period_start, period_end, *extra_params],
        )

        # Billing compliance (from billing_config if tracked)
        billable_tickets = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.client_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed')
               AND t.resolution_time >= ? AND t.resolution_time <= ?{extra_and_t}""",
            [client_id, period_start, period_end, *extra_params],
        )
        billed_tickets = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
               JOIN billing_config bc ON t.client_id = bc.client_id
               WHERE t.client_id = ? AND bc.track_billing = 1
               AND t.status IN ('Resolved', 'Closed')
               AND t.resolution_time >= ? AND t.resolution_time <= ?
               AND t.worklog_hours > 0{extra_and_t}""",
            [client_id, period_start, period_end, *extra_params],
        )
        billable_total = billable_tickets[0][0] or 0
        billing_compliance = round((billed_tickets[0][0] / billable_total * 100) if billable_total > 0 else 100, 1)

        ticket_volume = ticket_vol[0][0] or 0
        avg_fr_min = round(avg_fr[0][0] or 0, 1)
        avg_res_min = round(avg_res[0][0] or 0, 1)
        reopened_count = reopened[0][0] or 0

        health_score = _compute_health_score(
            sla_compliance,
            avg_fr_min,
            reopened_count,
            ticket_volume,
            billing_compliance,
        )

        result.append({
            "id": client_id,
            "name": client["name"],
            "ticket_volume": ticket_volume,
            "open_tickets": open_count[0][0],
            "closed_period": closed_period[0][0],
            "sla_compliance_pct": sla_compliance,
            "avg_first_response_minutes": avg_fr_min,
            "avg_resolution_minutes": avg_res_min,
            "billed_hours": billed_hours,
            "reopened_count": reopened_count,
            "health_score": health_score,
            "health_color": _health_color(health_score),
        })

    # Sort by health_score ascending (worst clients first)
    result.sort(key=lambda c: c["health_score"])

    return {"clients": result, "date_range_label": filters.date_range_label}


@router.get("/clients/profitability")
async def clients_profitability(request: Request, filters: FilterParams = Depends()):
    """Get profitability metrics for all clients with contract values."""
    db = request.app.state.db
    conn = await db.get_connection()
    settings = get_settings()
    tech_cost = settings.billing.tech_cost_per_hour

    now = _now_tz()
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else now.isoformat()

    # Get clients with billing config (including optional monthly_contract_value)
    clients = await conn.execute_fetchall("""
        SELECT c.id, c.name, bc.monthly_contract_value, bc.billing_type, bc.track_billing
        FROM clients c
        LEFT JOIN billing_config bc ON c.id = bc.client_id
        WHERE c.stage = 'Active'
        ORDER BY c.name
    """)

    result = []
    for client in clients:
        client_id = client["id"]
        contract_value = client["monthly_contract_value"]

        # Hours consumed in period
        hours_row = await conn.execute_fetchall(
            """SELECT SUM(worklog_hours) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time <= ?""",
            [client_id, period_start, period_end],
        )
        hours_consumed = round(hours_row[0][0] or 0, 2)

        # Ticket count
        ticket_row = await conn.execute_fetchall(
            """SELECT COUNT(*) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time <= ?""",
            [client_id, period_start, period_end],
        )
        ticket_count = ticket_row[0][0] or 0

        # Calculate profitability metrics
        service_cost = round(hours_consumed * tech_cost, 2)
        effective_hourly_rate = None
        gross_margin = None
        gross_margin_pct = None

        if contract_value and contract_value > 0:
            if hours_consumed > 0:
                effective_hourly_rate = round(contract_value / hours_consumed, 2)
            gross_margin = round(contract_value - service_cost, 2)
            gross_margin_pct = round((gross_margin / contract_value) * 100, 1) if contract_value > 0 else None

        result.append({
            "id": client_id,
            "name": client["name"],
            "billing_type": client["billing_type"] or "unknown",
            "monthly_contract_value": contract_value,
            "hours_consumed": hours_consumed,
            "ticket_count": ticket_count,
            "service_cost": service_cost,
            "effective_hourly_rate": effective_hourly_rate,
            "gross_margin": gross_margin,
            "gross_margin_pct": gross_margin_pct,
        })

    # Sort by hours consumed descending (for Pareto)
    result.sort(key=lambda c: c["hours_consumed"], reverse=True)

    # Add cumulative percentage for Pareto chart
    total_hours = sum(c["hours_consumed"] for c in result)
    cumulative = 0
    for c in result:
        cumulative += c["hours_consumed"]
        c["cumulative_hours_pct"] = round((cumulative / total_hours * 100) if total_hours > 0 else 0, 1)

    return {
        "clients": result,
        "tech_cost_per_hour": tech_cost,
        "date_range_label": filters.date_range_label,
    }


@router.get("/clients/{cid}")
async def client_detail(cid: str, request: Request, filters: FilterParams = Depends()):
    """Get detailed view for a specific client."""
    client_id = cid
    db = request.app.state.db
    conn = await db.get_connection()

    now = _now_tz()
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat() if filters.date_to else now.isoformat()

    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # Client info
    client_rows = await conn.execute_fetchall(
        "SELECT * FROM clients WHERE id = ?", (client_id,)
    )
    if not client_rows:
        return {"error": "Client not found"}

    client = client_rows[0]

    # KPI metrics
    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status NOT IN {CLOSED_STATUSES_SQL}{extra_and}",
        [client_id, *extra_params],
    )

    closed_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
        [client_id, period_start, period_end, *extra_params],
    )

    total_with_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE client_id = ? AND created_time >= ? AND created_time <= ?
           AND sla_name IS NOT NULL{extra_and}""",
        [client_id, period_start, period_end, *extra_params],
    )
    violated_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE client_id = ? AND created_time >= ? AND created_time <= ?
           AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
        [client_id, period_start, period_end, *extra_params],
    )
    total_sla = total_with_sla[0][0] or 0
    violated = violated_sla[0][0] or 0
    sla_compliance = round(((total_sla - violated) / total_sla * 100) if total_sla > 0 else 100, 1)

    avg_fr = await conn.execute_fetchall(
        f"""SELECT AVG(
            (julianday(first_response_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE client_id = ? AND first_response_time IS NOT NULL
        AND created_time >= ? AND created_time <= ?{extra_and}""",
        [client_id, period_start, period_end, *extra_params],
    )

    avg_res = await conn.execute_fetchall(
        f"""SELECT AVG(
            (julianday(resolution_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE client_id = ? AND resolution_time IS NOT NULL
        AND created_time >= ? AND created_time <= ?{extra_and}""",
        [client_id, period_start, period_end, *extra_params],
    )

    worklog = await conn.execute_fetchall(
        f"""SELECT SUM(worklog_hours) FROM tickets
           WHERE client_id = ? AND status IN {CLOSED_STATUSES_SQL}
           AND resolution_time >= ? AND resolution_time <= ?{extra_and}""",
        [client_id, period_start, period_end, *extra_params],
    )
    billed_hours = round(worklog[0][0] or 0, 1)

    # Open tickets list
    open_tickets_rows = await conn.execute_fetchall(
        f"""SELECT * FROM tickets
            WHERE client_id = ? AND status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            ORDER BY {PRIORITY_ORDER} DESC, first_response_due ASC""",
        [client_id, *extra_params],
    )

    provider = request.app.state.provider
    tickets = [ticket_row_to_dict(row) for row in open_tickets_rows]
    for t in tickets:
        t["url"] = provider.get_ticket_url(t["id"])

    # Category breakdown
    categories = await conn.execute_fetchall(
        f"""SELECT category, COUNT(*) as count FROM tickets
           WHERE client_id = ? AND category IS NOT NULL
           AND created_time >= ? AND created_time <= ?{extra_and}
           GROUP BY category ORDER BY count DESC""",
        [client_id, period_start, period_end, *extra_params],
    )

    # Technician breakdown
    technicians = await conn.execute_fetchall(
        f"""SELECT COALESCE(technician_name, 'Unassigned') as tech_name, COUNT(*) as count
           FROM tickets
           WHERE client_id = ? AND created_time >= ? AND created_time <= ?{extra_and}
           GROUP BY technician_name ORDER BY count DESC""",
        [client_id, period_start, period_end, *extra_params],
    )

    # SLA trend: weekly SLA compliance for last 12 weeks
    sla_trend = []
    for i in range(12, 0, -1):
        week_end = now - timedelta(weeks=i - 1)
        week_start = week_end - timedelta(weeks=1)
        we_iso = week_end.isoformat()
        ws_iso = week_start.isoformat()
        week_label = week_end.strftime("%Y-W%W")

        total_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time < ?
               AND sla_name IS NOT NULL{extra_and}""",
            [client_id, ws_iso, we_iso, *extra_params],
        )
        violated_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE client_id = ? AND created_time >= ? AND created_time < ?
               AND sla_name IS NOT NULL
               AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
            [client_id, ws_iso, we_iso, *extra_params],
        )
        week_total = total_row[0][0] or 0
        week_violated = violated_row[0][0] or 0
        week_compliance = round(((week_total - week_violated) / week_total * 100) if week_total > 0 else 100, 1)

        sla_trend.append({
            "week": week_label,
            "compliance_pct": week_compliance,
            "total": week_total,
            "violated": week_violated,
        })

    # Volume trend: weekly ticket volume for last 12 weeks
    volume_trend = []
    for i in range(12, 0, -1):
        week_end = now - timedelta(weeks=i - 1)
        week_start = week_end - timedelta(weeks=1)
        we_iso = week_end.isoformat()
        ws_iso = week_start.isoformat()
        week_label = week_end.strftime("%Y-W%W")

        created_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND created_time >= ? AND created_time < ?{extra_and}",
            [client_id, ws_iso, we_iso, *extra_params],
        )
        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE client_id = ? AND resolution_time >= ? AND resolution_time < ?{extra_and}",
            [client_id, ws_iso, we_iso, *extra_params],
        )
        volume_trend.append({
            "week": week_label,
            "created": created_row[0][0],
            "closed": closed_row[0][0],
        })

    return {
        "client": {
            "id": client["id"],
            "name": client["name"],
            "stage": client["stage"],
        },
        "kpis": {
            "open_tickets": open_count[0][0],
            "closed_period": closed_period[0][0],
            "sla_compliance_pct": sla_compliance,
            "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
            "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
            "billed_hours": billed_hours,
        },
        "open_tickets": tickets,
        "categories": [{"category": r["category"], "count": r["count"]} for r in categories],
        "technicians": [{"technician": r["tech_name"], "count": r["count"]} for r in technicians],
        "sla_trend": sla_trend,
        "volume_trend": volume_trend,
        "date_range_label": filters.date_range_label,
    }
