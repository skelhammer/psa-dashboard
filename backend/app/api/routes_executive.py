"""Executive Report API: CEO-focused KPIs with MoM and YoY comparisons."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL
from app.config import get_settings

router = APIRouter(prefix="/api", tags=["executive"])


def _now_tz() -> datetime:
    tz = ZoneInfo(get_settings().server.timezone)
    return datetime.now(tz)


def _prior_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Compute the equivalent prior period (same length, immediately before)."""
    length = end - start
    return start - length, start


def _year_ago_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Same calendar dates, one year earlier."""
    try:
        return start.replace(year=start.year - 1), end.replace(year=end.year - 1)
    except ValueError:
        # Handle leap year edge case (Feb 29)
        return start.replace(year=start.year - 1, day=28), end.replace(year=end.year - 1, day=28)


def _pct_change(current, previous):
    if previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _build_filter_sql(filters: FilterParams, prefix: str = "") -> tuple[str, list]:
    """Build AND-able filter conditions from FilterParams (no WHERE keyword, no dates)."""
    conditions = []
    params = []
    col = f"{prefix}." if prefix else ""

    if filters.provider:
        conditions.append(f"{col}provider = ?")
        params.append(filters.provider)
    if filters.hide_corp:
        conditions.append(f"{col}is_corp = 0")
    if filters.client_id:
        conditions.append(f"{col}client_id = ?")
        params.append(filters.client_id)
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


def _auto_intervals(start: datetime, end: datetime) -> list[tuple[datetime, datetime, str]]:
    """Generate time intervals with auto granularity based on period length.

    < 14 days: daily
    14-90 days: weekly
    > 90 days: monthly
    """
    days = (end - start).days
    intervals = []

    if days <= 14:
        d = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while d < end:
            next_d = d + timedelta(days=1)
            intervals.append((d, min(next_d, end), d.strftime("%b %d")))
            d = next_d
    elif days <= 90:
        d = start.replace(hour=0, minute=0, second=0, microsecond=0)
        d = d - timedelta(days=d.weekday())
        while d < end:
            next_d = d + timedelta(weeks=1)
            intervals.append((d, min(next_d, end), d.strftime("%b %d")))
            d = next_d
    else:
        d = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while d < end:
            if d.month == 12:
                next_d = d.replace(year=d.year + 1, month=1)
            else:
                next_d = d.replace(month=d.month + 1)
            intervals.append((d, min(next_d, end), d.strftime("%b %Y")))
            d = next_d

    return intervals


async def _period_metrics(conn, start_iso: str, end_iso: str, extra_sql: str = "", extra_params: list | None = None) -> dict:
    """Compute all KPI metrics for a given date range with optional extra filters."""
    ep = extra_params or []
    extra = f" AND {extra_sql}" if extra_sql else ""

    # Tickets created
    created = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    # Tickets closed
    closed = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    # Avg first response (business minutes)
    avg_fr = await conn.execute_fetchall(
        f"SELECT AVG(first_response_business_minutes) FROM tickets WHERE first_response_business_minutes > 0 AND created_time >= ? AND created_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    # Avg resolution (business minutes)
    avg_res = await conn.execute_fetchall(
        f"SELECT AVG(resolution_business_minutes) FROM tickets WHERE resolution_business_minutes > 0 AND created_time >= ? AND created_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    # SLA compliance
    total_sla = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL{extra}",
        [start_iso, end_iso] + ep,
    )
    violated_sla = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL AND (first_response_violated = 1 OR resolution_violated = 1){extra}",
        [start_iso, end_iso] + ep,
    )
    total_s = total_sla[0][0] or 0
    violated_s = violated_sla[0][0] or 0
    sla_pct = round(((total_s - violated_s) / total_s * 100) if total_s > 0 else 100, 1)

    # Total worklog hours
    worklog = await conn.execute_fetchall(
        f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    worklog_hours = round(worklog[0][0] or 0, 1)

    # Reopened
    reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE reopened = 1 AND updated_time >= ? AND updated_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )

    # FCR (First Call Resolution) rate for closed tickets in period
    fcr_total = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra}",
        [start_iso, end_iso] + ep,
    )
    fcr_yes = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ? AND fcr = 1{extra}",
        [start_iso, end_iso] + ep,
    )
    fcr_total_val = fcr_total[0][0] or 0
    fcr_yes_val = fcr_yes[0][0] or 0
    fcr_rate = round((fcr_yes_val / fcr_total_val * 100) if fcr_total_val > 0 else 0, 1)

    # Billing compliance: % of billable client tickets (resolved) with worklog > 0
    extra_t = extra.replace('client_id', 't.client_id').replace('technician_id', 't.technician_id').replace('priority', 't.priority').replace('category', 't.category').replace('tech_group_name', 't.tech_group_name')
    billable_total = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets t
            JOIN billing_config bc ON t.client_id = bc.client_id AND bc.track_billing = 1
            WHERE t.status IN {CLOSED_STATUSES_SQL}
              AND t.resolution_time >= ? AND t.resolution_time < ?{extra_t}""",
        [start_iso, end_iso] + ep,
    )
    billable_with_time = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets t
            JOIN billing_config bc ON t.client_id = bc.client_id AND bc.track_billing = 1
            WHERE t.status IN {CLOSED_STATUSES_SQL}
              AND t.resolution_time >= ? AND t.resolution_time < ?
              AND t.worklog_hours > 0{extra_t}""",
        [start_iso, end_iso] + ep,
    )
    bt = billable_total[0][0] or 0
    bw = billable_with_time[0][0] or 0
    billing_pct = round((bw / bt * 100) if bt > 0 else 100, 1)

    return {
        "tickets_created": created[0][0] or 0,
        "tickets_closed": closed[0][0] or 0,
        "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
        "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
        "sla_compliance_pct": sla_pct,
        "total_worklog_hours": worklog_hours,
        "reopened_count": reopened[0][0] or 0,
        "fcr_rate": fcr_rate,
        "billing_compliance_pct": billing_pct,
    }


@router.get("/executive/report")
async def executive_report(request: Request, filters: FilterParams = Depends()):
    db = request.app.state.db
    conn = await db.get_connection()

    start = filters.date_from
    end = filters.date_to
    label = filters.date_range_label
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    # Build extra filter SQL (non-date filters)
    extra_sql, extra_params = _build_filter_sql(filters)

    # Current period metrics
    current = await _period_metrics(conn, start_iso, end_iso, extra_sql, extra_params)

    # Open backlog (current snapshot)
    backlog_extra = f" AND {extra_sql}" if extra_sql else ""
    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{backlog_extra}",
        extra_params,
    )
    current["open_backlog"] = open_count[0][0] or 0

    # Unresolved billing flags
    flags = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
    )
    current["unresolved_billing_flags"] = flags[0][0] or 0

    # Team utilization (only technician-role techs)
    techs = await conn.execute_fetchall(
        "SELECT available_hours_per_week FROM technicians WHERE COALESCE(dashboard_role, 'technician') LIKE '%technician%'"
    )
    if techs:
        weeks_in_period = max((end - start).days / 7, 1)
        total_available = sum((t[0] or 40) * weeks_in_period for t in techs)
        total_worked = await conn.execute_fetchall(
            f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time < ?{backlog_extra}",
            [start_iso, end_iso] + extra_params,
        )
        worked = total_worked[0][0] or 0
        current["team_utilization_pct"] = round((worked / total_available * 100) if total_available > 0 else 0, 1)
    else:
        current["team_utilization_pct"] = 0

    # MoM comparison
    mom_start, mom_end = _prior_period(start, end)
    mom = await _period_metrics(conn, mom_start.isoformat(), mom_end.isoformat(), extra_sql, extra_params)

    # YoY comparison
    yoy_start, yoy_end = _year_ago_period(start, end)
    yoy = await _period_metrics(conn, yoy_start.isoformat(), yoy_end.isoformat(), extra_sql, extra_params)

    compare_keys = [
        "tickets_created", "tickets_closed", "avg_first_response_minutes",
        "avg_resolution_minutes", "sla_compliance_pct", "total_worklog_hours",
        "reopened_count", "fcr_rate", "billing_compliance_pct",
    ]
    mom_change = {k: _pct_change(current[k], mom[k]) for k in compare_keys}
    yoy_change = {k: _pct_change(current[k], yoy[k]) for k in compare_keys}

    return {
        "period_label": label,
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
        "kpis": current,
        "mom_change": mom_change,
        "yoy_change": yoy_change,
    }


@router.get("/executive/charts")
async def executive_charts(request: Request, filters: FilterParams = Depends()):
    db = request.app.state.db
    conn = await db.get_connection()
    now = _now_tz()

    start = filters.date_from
    end = filters.date_to
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    # Build extra filter SQL (non-date filters)
    extra_sql, extra_params = _build_filter_sql(filters)
    extra = f" AND {extra_sql}" if extra_sql else ""
    extra_t = extra.replace('client_id', 't.client_id').replace('technician_id', 't.technician_id').replace('priority', 't.priority').replace('category', 't.category').replace('tech_group_name', 't.tech_group_name')

    # Auto-granularity intervals
    intervals = _auto_intervals(start, end)

    # Volume: current period vs prior year same period (auto-granularity)
    volume_comparison = []
    for iv_start, iv_end, label in intervals:
        cur = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
            [iv_start.isoformat(), iv_end.isoformat()] + extra_params,
        )
        try:
            py_start = iv_start.replace(year=iv_start.year - 1)
            py_end = iv_end.replace(year=iv_end.year - 1)
        except ValueError:
            py_start = iv_start.replace(year=iv_start.year - 1, day=28)
            py_end = iv_end.replace(year=iv_end.year - 1, day=28)
        prev = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
            [py_start.isoformat(), py_end.isoformat()] + extra_params,
        )
        volume_comparison.append({
            "label": label,
            "current_year": cur[0][0] or 0,
            "prior_year": prev[0][0] or 0,
        })

    # SLA compliance trend (auto-granularity)
    sla_trend = []
    for iv_start, iv_end, label in intervals:
        total = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL{extra}",
            [iv_start.isoformat(), iv_end.isoformat()] + extra_params,
        )
        violated = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL AND (first_response_violated = 1 OR resolution_violated = 1){extra}",
            [iv_start.isoformat(), iv_end.isoformat()] + extra_params,
        )
        t = total[0][0] or 0
        v = violated[0][0] or 0
        pct = round(((t - v) / t * 100) if t > 0 else 100, 1)
        sla_trend.append({
            "label": label,
            "compliance_pct": pct,
            "total": t,
            "violated": v,
        })

    # Backlog trend: opened, closed, open snapshot per interval (moved from overview)
    backlog_trend = []
    for iv_start, iv_end, label in intervals:
        opened_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE resolution_time >= ? AND resolution_time < ?{extra}",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        # Snapshot: tickets open at end of interval
        snapshot = iv_end.isoformat()
        open_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
                WHERE created_time < ?
                AND (
                    (resolution_time IS NOT NULL AND resolution_time >= ?)
                    OR (resolution_time IS NULL AND status NOT IN {CLOSED_STATUSES_SQL})
                ){extra}""",
            [snapshot, snapshot, *extra_params],
        )
        backlog_trend.append({
            "label": label,
            "opened": opened_row[0][0] or 0,
            "closed": closed_row[0][0] or 0,
            "open_count": open_row[0][0] or 0,
        })

    # Team performance summary (only technician-role techs)
    tech_rows = await conn.execute_fetchall(
        "SELECT id, first_name, last_name, available_hours_per_week FROM technicians WHERE COALESCE(dashboard_role, 'technician') LIKE '%technician%'"
    )
    team_summary = []
    weeks_in_period = max((end - start).days / 7, 1)
    for tech in tech_rows:
        tid = tech[0]
        name = f"{tech[1]} {tech[2]}".strip()
        avail = (tech[3] or 40) * weeks_in_period

        tech_extra = f"technician_id = ?{' AND ' + extra_sql if extra_sql else ''}"
        tech_params = [tid] + extra_params

        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ? AND {tech_extra}",
            [start_iso, end_iso] + tech_params,
        )
        sla_total = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL AND {tech_extra}",
            [start_iso, end_iso] + tech_params,
        )
        sla_violated = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL AND (first_response_violated = 1 OR resolution_violated = 1) AND {tech_extra}",
            [start_iso, end_iso] + tech_params,
        )
        avg_res_row = await conn.execute_fetchall(
            f"SELECT AVG(resolution_business_minutes) FROM tickets WHERE resolution_business_minutes > 0 AND created_time >= ? AND created_time < ? AND {tech_extra}",
            [start_iso, end_iso] + tech_params,
        )
        worklog_row = await conn.execute_fetchall(
            f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time < ? AND {tech_extra}",
            [start_iso, end_iso] + tech_params,
        )
        open_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND {tech_extra}",
            tech_params,
        )

        st = sla_total[0][0] or 0
        sv = sla_violated[0][0] or 0
        sla_pct = round(((st - sv) / st * 100) if st > 0 else 100, 1)
        worked = worklog_row[0][0] or 0
        util = round((worked / avail * 100) if avail > 0 else 0, 1)

        team_summary.append({
            "name": name,
            "open_tickets": open_row[0][0] or 0,
            "closed": closed_row[0][0] or 0,
            "sla_pct": sla_pct,
            "utilization_pct": util,
            "avg_resolution_minutes": round(avg_res_row[0][0] or 0, 1),
            "worklog_hours": round(worked, 1),
        })

    team_summary.sort(key=lambda t: t["closed"], reverse=True)

    # Top 10 clients by volume (selected period)
    top_clients = await conn.execute_fetchall(
        f"""SELECT COALESCE(client_name, 'Unassigned') as client_name, COUNT(*) as volume,
                   SUM(CASE WHEN sla_name IS NOT NULL AND (first_response_violated = 1 OR resolution_violated = 1) THEN 1 ELSE 0 END) as violated,
                   SUM(CASE WHEN sla_name IS NOT NULL THEN 1 ELSE 0 END) as sla_total
            FROM tickets
            WHERE created_time >= ? AND created_time < ?{extra}
            GROUP BY COALESCE(client_name, 'Unassigned')
            ORDER BY volume DESC
            LIMIT 10""",
        [start_iso, end_iso] + extra_params,
    )
    top_clients_data = []
    for r in top_clients:
        st = r["sla_total"] or 0
        sv = r["violated"] or 0
        sla_pct = round(((st - sv) / st * 100) if st > 0 else 100, 1)
        top_clients_data.append({
            "name": r["client_name"] or "Unassigned",
            "volume": r["volume"],
            "sla_pct": sla_pct,
        })

    # Resolution time distribution (selected period)
    res_times = await conn.execute_fetchall(
        f"SELECT resolution_business_minutes FROM tickets WHERE resolution_business_minutes > 0 AND created_time >= ? AND created_time < ?{extra}",
        [start_iso, end_iso] + extra_params,
    )
    buckets = {"< 1h": 0, "1-4h": 0, "4-8h": 0, "1-2d": 0, "2d+": 0}
    for r in res_times:
        mins = r[0]
        if mins < 60:
            buckets["< 1h"] += 1
        elif mins < 240:
            buckets["1-4h"] += 1
        elif mins < 480:
            buckets["4-8h"] += 1
        elif mins < 960:
            buckets["1-2d"] += 1
        else:
            buckets["2d+"] += 1

    # Billing compliance trend (auto-granularity)
    billing_trend = []
    for iv_start, iv_end, label in intervals:
        bt_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
                JOIN billing_config bc ON t.client_id = bc.client_id AND bc.track_billing = 1
                WHERE t.status IN {CLOSED_STATUSES_SQL}
                  AND t.resolution_time >= ? AND t.resolution_time < ?{extra_t}""",
            [iv_start.isoformat(), iv_end.isoformat()] + extra_params,
        )
        bw_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets t
                JOIN billing_config bc ON t.client_id = bc.client_id AND bc.track_billing = 1
                WHERE t.status IN {CLOSED_STATUSES_SQL}
                  AND t.resolution_time >= ? AND t.resolution_time < ?
                  AND t.worklog_hours > 0{extra_t}""",
            [iv_start.isoformat(), iv_end.isoformat()] + extra_params,
        )
        bt_val = bt_row[0][0] or 0
        bw_val = bw_row[0][0] or 0
        pct = round((bw_val / bt_val * 100) if bt_val > 0 else 100, 1)
        billing_trend.append({
            "label": label,
            "compliance_pct": pct,
            "total": bt_val,
            "billed": bw_val,
        })

    # Category distribution (moved from overview, selected period)
    category_dist = await conn.execute_fetchall(
        f"""SELECT COALESCE(category, 'Uncategorized') as category, COUNT(*) as count
            FROM tickets WHERE created_time >= ? AND created_time < ?{extra}
            GROUP BY category ORDER BY count DESC LIMIT 10""",
        [start_iso, end_iso] + extra_params,
    )
    category_chart = [{"category": r["category"], "count": r["count"]} for r in category_dist]

    return {
        "volume_comparison": volume_comparison,
        "sla_trend": sla_trend,
        "backlog_trend": backlog_trend,
        "team_summary": team_summary,
        "top_clients": top_clients_data,
        "resolution_distribution": [{"bucket": k, "count": v} for k, v in buckets.items()],
        "billing_trend": billing_trend,
        "category_distribution": category_chart,
    }


@router.get("/executive/financials")
async def executive_financials(request: Request, filters: FilterParams = Depends()):
    """Portfolio-level profitability summary for the executive report."""
    db = request.app.state.db
    conn = await db.get_connection()
    settings = get_settings()
    tech_cost = settings.billing.tech_cost_per_hour

    start = filters.date_from
    end = filters.date_to
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    extra_sql, extra_params = _build_filter_sql(filters)
    extra = f" AND {extra_sql}" if extra_sql else ""

    async def _portfolio_metrics(s_iso: str, e_iso: str) -> dict:
        """Compute portfolio financials for a given period."""
        # Total monthly contract revenue (all active clients with contracts)
        rev_row = await conn.execute_fetchall(
            """SELECT SUM(bc.monthly_contract_value) FROM billing_config bc
               JOIN clients c ON c.id = bc.client_id
               WHERE c.stage = 'Active' AND bc.monthly_contract_value > 0"""
        )
        total_revenue = rev_row[0][0] or 0

        # Total service cost = worklog hours * tech cost in period
        cost_row = await conn.execute_fetchall(
            f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time < ?{extra}",
            [s_iso, e_iso] + extra_params,
        )
        total_hours = cost_row[0][0] or 0
        total_service_cost = round(total_hours * tech_cost, 2)

        # Tickets closed in period (for cost per ticket)
        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra}",
            [s_iso, e_iso] + extra_params,
        )
        tickets_closed = closed_row[0][0] or 0

        # Compute derived metrics
        blended_margin_pct = round(((total_revenue - total_service_cost) / total_revenue * 100) if total_revenue > 0 else 0, 1)
        cost_per_ticket = round(total_service_cost / tickets_closed, 2) if tickets_closed > 0 else 0

        return {
            "total_revenue": round(total_revenue, 2),
            "total_service_cost": total_service_cost,
            "blended_margin_pct": blended_margin_pct,
            "cost_per_ticket": cost_per_ticket,
            "total_hours": round(total_hours, 1),
            "tickets_closed": tickets_closed,
        }

    current = await _portfolio_metrics(start_iso, end_iso)

    # MoM comparison
    mom_start, mom_end = _prior_period(start, end)
    prior = await _portfolio_metrics(mom_start.isoformat(), mom_end.isoformat())

    comparison = {
        "total_revenue_pct": _pct_change(current["total_revenue"], prior["total_revenue"]),
        "blended_margin_pct": _pct_change(current["blended_margin_pct"], prior["blended_margin_pct"]),
        "cost_per_ticket_pct": _pct_change(current["cost_per_ticket"], prior["cost_per_ticket"]),
    }

    return {
        **current,
        "comparison": comparison,
        "date_range_label": filters.date_range_label,
    }
