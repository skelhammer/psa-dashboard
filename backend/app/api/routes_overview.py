"""Overview / Home API: KPI cards and chart data."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL
from app.config import get_settings

router = APIRouter(prefix="/api", tags=["overview"])


def _now_tz() -> datetime:
    tz = ZoneInfo(get_settings().server.timezone)
    return datetime.now(tz)


def _build_filter_sql(filters: FilterParams, prefix: str = "") -> tuple[str, list]:
    """Build AND-able filter conditions from FilterParams (no WHERE keyword)."""
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
        # Daily
        d = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while d < end:
            next_d = d + timedelta(days=1)
            intervals.append((d, min(next_d, end), d.strftime("%b %d")))
            d = next_d
    elif days <= 90:
        # Weekly
        d = start.replace(hour=0, minute=0, second=0, microsecond=0)
        # Align to Monday
        d = d - timedelta(days=d.weekday())
        while d < end:
            next_d = d + timedelta(weeks=1)
            intervals.append((d, min(next_d, end), d.strftime("%b %d")))
            d = next_d
    else:
        # Monthly
        d = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while d < end:
            if d.month == 12:
                next_d = d.replace(year=d.year + 1, month=1)
            else:
                next_d = d.replace(month=d.month + 1)
            intervals.append((d, min(next_d, end), d.strftime("%b %Y")))
            d = next_d

    return intervals


@router.get("/overview")
async def overview(request: Request, filters: FilterParams = Depends()):
    db = request.app.state.db
    conn = await db.get_connection()

    now = _now_tz()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    # Use the filter's resolved date range for period-based metrics
    period_start = filters.date_from.isoformat()
    period_end = filters.date_to.isoformat()

    # Extra filter conditions (client, tech, priority, category)
    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # Total open tickets
    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}",
        extra_params,
    )

    # Tickets created in selected period
    created_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time <= ?{extra_and}",
        [period_start, period_end, *extra_params],
    )

    # Tickets created today
    created_today = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ?{extra_and}",
        [today_start.isoformat(), *extra_params],
    )

    # Tickets closed today
    closed_today = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?{extra_and}",
        [today_start.isoformat(), *extra_params],
    )

    # Tickets created this week
    created_week = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ?{extra_and}",
        [week_start.isoformat(), *extra_params],
    )

    # Closed in selected period
    closed_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}",
        [period_start, period_end, *extra_params],
    )

    # Closed this week
    closed_week = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?{extra_and}",
        [week_start.isoformat(), *extra_params],
    )

    # Average first response time (selected period, in business minutes)
    avg_fr = await conn.execute_fetchall(
        f"""SELECT AVG(first_response_business_minutes) FROM tickets
        WHERE first_response_business_minutes > 0 AND created_time >= ? AND created_time <= ?{extra_and}""",
        [period_start, period_end, *extra_params],
    )

    # Average resolution time (selected period, in business minutes)
    avg_res = await conn.execute_fetchall(
        f"""SELECT AVG(resolution_business_minutes) FROM tickets
        WHERE resolution_business_minutes > 0 AND created_time >= ? AND created_time <= ?{extra_and}""",
        [period_start, period_end, *extra_params],
    )

    # SLA compliance rate (selected period)
    total_with_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND created_time <= ? AND sla_name IS NOT NULL{extra_and}""",
        [period_start, period_end, *extra_params],
    )
    violated_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND created_time <= ? AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
        [period_start, period_end, *extra_params],
    )

    total_sla = total_with_sla[0][0] or 0
    violated = violated_sla[0][0] or 0
    sla_compliance = round(((total_sla - violated) / total_sla * 100) if total_sla > 0 else 100, 1)

    # Total worklog hours (selected period)
    worklog = await conn.execute_fetchall(
        f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time <= ?{extra_and}",
        [period_start, period_end, *extra_params],
    )
    total_worklog_hours = round(worklog[0][0] or 0, 1)

    # Unresolved billing flags
    if extra_sql:
        billing_flags = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM billing_flags bf
                JOIN tickets t ON bf.ticket_id = t.id
                WHERE bf.resolved = 0 AND {extra_sql.replace('client_id', 't.client_id').replace('technician_id', 't.technician_id').replace('priority', 't.priority').replace('category', 't.category')}""",
            extra_params,
        )
    else:
        billing_flags = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
        )

    # Reopened tickets in selected period (by updated_time, since that's when they were reopened)
    reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE reopened = 1 AND updated_time >= ? AND updated_time <= ?{extra_and}",
        [period_start, period_end, *extra_params],
    )

    # FCR (First Call Resolution) rate for closed tickets in period
    fcr_total = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ?{extra_and}""",
        [period_start, period_end, *extra_params],
    )
    fcr_yes = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time <= ? AND fcr = 1{extra_and}""",
        [period_start, period_end, *extra_params],
    )
    fcr_total_val = fcr_total[0][0] or 0
    fcr_yes_val = fcr_yes[0][0] or 0
    fcr_rate = round((fcr_yes_val / fcr_total_val * 100) if fcr_total_val > 0 else 0, 1)

    # --- Period-over-period comparison ---
    period_length = filters.date_to - filters.date_from
    prev_end = filters.date_from
    prev_start = prev_end - period_length
    prev_start_iso = prev_start.isoformat()
    prev_end_iso = prev_end.isoformat()

    prev_created = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra_and}",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_closed = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra_and}",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_avg_fr = await conn.execute_fetchall(
        f"""SELECT AVG(first_response_business_minutes) FROM tickets
        WHERE first_response_business_minutes > 0 AND created_time >= ? AND created_time < ?{extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_avg_res = await conn.execute_fetchall(
        f"""SELECT AVG(resolution_business_minutes) FROM tickets
        WHERE resolution_business_minutes > 0 AND created_time >= ? AND created_time < ?{extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_total_with_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL{extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_violated_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_total_sla_val = prev_total_with_sla[0][0] or 0
    prev_violated_val = prev_violated_sla[0][0] or 0
    prev_sla_compliance = round(((prev_total_sla_val - prev_violated_val) / prev_total_sla_val * 100) if prev_total_sla_val > 0 else 100, 1)

    prev_worklog = await conn.execute_fetchall(
        f"SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= ? AND created_time < ?{extra_and}",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_worklog_hours = round(prev_worklog[0][0] or 0, 1)

    prev_reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE reopened = 1 AND updated_time >= ? AND updated_time < ?{extra_and}",
        [prev_start_iso, prev_end_iso, *extra_params],
    )

    prev_fcr_total = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_fcr_yes = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ? AND fcr = 1{extra_and}""",
        [prev_start_iso, prev_end_iso, *extra_params],
    )
    prev_fcr_total_val = prev_fcr_total[0][0] or 0
    prev_fcr_yes_val = prev_fcr_yes[0][0] or 0
    prev_fcr_rate = round((prev_fcr_yes_val / prev_fcr_total_val * 100) if prev_fcr_total_val > 0 else 0, 1)

    def pct_change(current, previous):
        if previous is None or previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    created_p = created_period[0][0]
    closed_p = closed_period[0][0]
    avg_fr_val = round(avg_fr[0][0] or 0, 1)
    avg_res_val = round(avg_res[0][0] or 0, 1)
    reopened_val = reopened[0][0]

    settings = get_settings()

    return {
        "kpis": {
            "total_open": open_count[0][0],
            "created_today": created_today[0][0],
            "closed_today": closed_today[0][0],
            "created_this_week": created_week[0][0],
            "created_period": created_p,
            "closed_period": closed_p,
            "closed_this_week": closed_week[0][0],
            "net_flow_today": created_today[0][0] - closed_today[0][0],
            "net_flow_period": created_p - closed_p,
            "avg_first_response_minutes": avg_fr_val,
            "avg_resolution_minutes": avg_res_val,
            "sla_compliance_pct": sla_compliance,
            "total_worklog_hours": total_worklog_hours,
            "unresolved_billing_flags": billing_flags[0][0],
            "reopened_period": reopened_val,
            "fcr_rate": fcr_rate,
            "fcr_count": fcr_yes_val,
            "fcr_total": fcr_total_val,
            "open_vs_closed_ratio": {
                "opened": created_week[0][0],
                "closed": closed_week[0][0],
            },
        },
        "pct_change": {
            "created_period": pct_change(created_p, prev_created[0][0]),
            "closed_period": pct_change(closed_p, prev_closed[0][0]),
            "avg_first_response_minutes": pct_change(avg_fr_val, round(prev_avg_fr[0][0] or 0, 1)),
            "avg_resolution_minutes": pct_change(avg_res_val, round(prev_avg_res[0][0] or 0, 1)),
            "sla_compliance_pct": pct_change(sla_compliance, prev_sla_compliance),
            "total_worklog_hours": pct_change(total_worklog_hours, prev_worklog_hours),
            "reopened_period": pct_change(reopened_val, prev_reopened[0][0]),
            "fcr_rate": pct_change(fcr_rate, prev_fcr_rate),
        },
        "date_range_label": filters.date_range_label,
        "thresholds": {
            "first_response_target_minutes": settings.thresholds.first_response_target_minutes,
            "resolution_target_minutes": settings.thresholds.resolution_target_minutes,
        },
    }


@router.get("/overview/charts")
async def overview_charts(request: Request, filters: FilterParams = Depends()):
    """Chart data: volume trend, aging buckets, workload balance, SLA trend."""
    db = request.app.state.db
    conn = await db.get_connection()
    now = _now_tz()

    start = filters.date_from
    end = filters.date_to
    period_start = start.isoformat()

    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # Auto-granularity intervals for the selected date range
    intervals = _auto_intervals(start, end)
    days = (end - start).days
    volume_granularity = "day" if days <= 14 else ("week" if days <= 90 else "month")

    # Volume trend: tickets created and closed per interval
    volume_trend = []
    for iv_start, iv_end, label in intervals:
        created_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra_and}",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ? AND resolution_time < ?{extra_and}",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        volume_trend.append({
            "date": label,
            "created": created_row[0][0] or 0,
            "closed": closed_row[0][0] or 0,
            "count": created_row[0][0] or 0,  # backward compat
        })

    # Aging buckets: open tickets by age
    aging_buckets = {"0-1d": 0, "1-3d": 0, "3-7d": 0, "7-14d": 0, "14d+": 0}
    open_tickets = await conn.execute_fetchall(
        f"SELECT created_time FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}",
        extra_params,
    )
    for row in open_tickets:
        try:
            created = datetime.fromisoformat(row["created_time"])
            age_days = (now.replace(tzinfo=None) - created).total_seconds() / 86400
            if age_days <= 1:
                aging_buckets["0-1d"] += 1
            elif age_days <= 3:
                aging_buckets["1-3d"] += 1
            elif age_days <= 7:
                aging_buckets["3-7d"] += 1
            elif age_days <= 14:
                aging_buckets["7-14d"] += 1
            else:
                aging_buckets["14d+"] += 1
        except (ValueError, TypeError):
            pass

    # Status distribution
    status_dist = await conn.execute_fetchall(
        f"""SELECT status, COUNT(*) as count FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY status ORDER BY count DESC""",
        extra_params,
    )
    status_chart = [{"status": r["status"], "count": r["count"]} for r in status_dist]

    # Priority distribution
    priority_dist = await conn.execute_fetchall(
        f"""SELECT priority, COUNT(*) as count FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY priority ORDER BY count DESC""",
        extra_params,
    )
    priority_chart = [{"priority": r["priority"], "count": r["count"]} for r in priority_dist]

    # Workload balance: open tickets per tech (group by ID to merge cross-provider names)
    workload = await conn.execute_fetchall(
        f"""SELECT
                COALESCE(technician_id, '') as tid,
                COALESCE(
                    (SELECT t2.first_name || ' ' || t2.last_name FROM technicians t2 WHERE t2.id = tickets.technician_id),
                    technician_name,
                    'Unassigned'
                ) as tech,
                COUNT(*) as count
            FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY COALESCE(technician_id, '') ORDER BY count DESC""",
        extra_params,
    )
    workload_chart = [{"technician": r["tech"].strip() or "Unassigned", "count": r["count"]} for r in workload]

    # Tickets by tech group (open tickets); null group treated as Tier 1 Support
    group_dist = await conn.execute_fetchall(
        f"""SELECT COALESCE(tech_group_name, 'Tier 1 Support') as group_name, COUNT(*) as count
            FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY group_name ORDER BY count DESC""",
        extra_params,
    )
    group_chart = [{"group": r["group_name"], "count": r["count"]} for r in group_dist]

    # Category distribution (open tickets)
    category_dist = await conn.execute_fetchall(
        f"""SELECT COALESCE(category, 'Uncategorized') as cat, COUNT(*) as count FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY cat ORDER BY count DESC""",
        extra_params,
    )
    category_chart = [{"category": r["cat"], "count": r["count"]} for r in category_dist]

    # Subcategory distribution (open tickets)
    subcategory_dist = await conn.execute_fetchall(
        f"""SELECT COALESCE(subcategory, 'Uncategorized') as subcat, COUNT(*) as count FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{extra_and}
            GROUP BY subcat ORDER BY count DESC""",
        extra_params,
    )
    subcategory_chart = [{"subcategory": r["subcat"], "count": r["count"]} for r in subcategory_dist]

    # Daily new tickets: one bar per day for up to the last 30 days of the
    # selected period. Single GROUP BY query (vs the per-day loop the prior
    # implementation used) so the chart adds at most 1 SQL query, not 30.
    daily_start = max(start, end - timedelta(days=30))
    daily_start = daily_start.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_end = end + timedelta(days=1)
    daily_rows = await conn.execute_fetchall(
        f"""SELECT date(created_time) as day, COUNT(*) as count
            FROM tickets
            WHERE created_time >= ? AND created_time < ?{extra_and}
            GROUP BY date(created_time)""",
        [daily_start.isoformat(), daily_end.isoformat(), *extra_params],
    )
    counts_by_day = {r["day"]: r["count"] for r in daily_rows}
    daily_new = []
    d = daily_start
    while d <= end:
        iso_day = d.strftime("%Y-%m-%d")
        daily_new.append({
            "date": d.strftime("%b %d"),
            "day": d.strftime("%a"),
            "count": counts_by_day.get(iso_day, 0),
        })
        d = d + timedelta(days=1)

    # SLA compliance trend (auto-granularity)
    sla_trend = []
    for iv_start, iv_end, label in intervals:
        total_sla_iv = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL{extra_and}""",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        violated_sla_iv = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
               WHERE created_time >= ? AND created_time < ? AND sla_name IS NOT NULL
               AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
            [iv_start.isoformat(), iv_end.isoformat(), *extra_params],
        )
        total_count = total_sla_iv[0][0] or 0
        violated_count = violated_sla_iv[0][0] or 0
        compliance = round(((total_count - violated_count) / total_count * 100) if total_count > 0 else 100, 1)
        sla_trend.append({
            "label": label,
            "compliance_pct": compliance,
            "total": total_count,
            "violated": violated_count,
        })

    return {
        "volume_trend": volume_trend,
        "volume_granularity": volume_granularity,
        "daily_new_tickets": daily_new,
        "aging_buckets": [{"bucket": k, "count": v} for k, v in aging_buckets.items()],
        "status_distribution": status_chart,
        "priority_distribution": priority_chart,
        "workload_balance": workload_chart,
        "group_distribution": group_chart,
        "category_distribution": category_chart,
        "subcategory_distribution": subcategory_chart,
        "sla_trend": sla_trend,
    }
