"""Overview / Home API: KPI cards and chart data."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL, OPEN_STATUSES_SQL
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

    return " AND ".join(conditions), params


@router.get("/overview")
async def overview(request: Request, filters: FilterParams = Depends()):
    db = request.app.state.db
    conn = await db.get_connection()

    now = _now_tz()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    # Use the filter's resolved date range for period-based metrics
    period_start = filters.date_from.isoformat()

    # Extra filter conditions (client, tech, priority, category)
    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # Total open tickets
    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {OPEN_STATUSES_SQL}{extra_and}",
        extra_params,
    )

    # Tickets created in selected period
    created_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ?{extra_and}",
        [period_start, *extra_params],
    )

    # Tickets created today
    created_today = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ?{extra_and}",
        [today_start.isoformat(), *extra_params],
    )

    # Tickets created this week
    created_week = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE created_time >= ?{extra_and}",
        [week_start.isoformat(), *extra_params],
    )

    # Closed in selected period
    closed_period = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?{extra_and}",
        [period_start, *extra_params],
    )

    # Closed this week
    closed_week = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?{extra_and}",
        [week_start.isoformat(), *extra_params],
    )

    # Average first response time (selected period, in minutes)
    avg_fr = await conn.execute_fetchall(
        f"""SELECT AVG(
            (julianday(first_response_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE first_response_time IS NOT NULL AND created_time >= ?{extra_and}""",
        [period_start, *extra_params],
    )

    # Average resolution time (selected period, in minutes)
    avg_res = await conn.execute_fetchall(
        f"""SELECT AVG(
            (julianday(resolution_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE resolution_time IS NOT NULL AND created_time >= ?{extra_and}""",
        [period_start, *extra_params],
    )

    # SLA compliance rate (selected period)
    total_with_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND sla_name IS NOT NULL{extra_and}""",
        [period_start, *extra_params],
    )
    violated_sla = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1){extra_and}""",
        [period_start, *extra_params],
    )

    total_sla = total_with_sla[0][0] or 0
    violated = violated_sla[0][0] or 0
    sla_compliance = round(((total_sla - violated) / total_sla * 100) if total_sla > 0 else 100, 1)

    # Total worklog hours (selected period)
    worklog = await conn.execute_fetchall(
        f"SELECT SUM(worklog_minutes) FROM tickets WHERE created_time >= ?{extra_and}",
        [period_start, *extra_params],
    )
    total_worklog_hours = round((worklog[0][0] or 0) / 60, 1)

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

    # Reopened tickets in selected period
    reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE reopened = 1 AND created_time >= ?{extra_and}",
        [period_start, *extra_params],
    )

    return {
        "kpis": {
            "total_open": open_count[0][0],
            "created_today": created_today[0][0],
            "created_this_week": created_week[0][0],
            "created_period": created_period[0][0],
            "closed_period": closed_period[0][0],
            "closed_this_week": closed_week[0][0],
            "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
            "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
            "sla_compliance_pct": sla_compliance,
            "total_worklog_hours": total_worklog_hours,
            "unresolved_billing_flags": billing_flags[0][0],
            "reopened_period": reopened[0][0],
            "open_vs_closed_ratio": {
                "opened": created_week[0][0],
                "closed": closed_week[0][0],
            },
        },
        "date_range_label": filters.date_range_label,
    }


@router.get("/overview/charts")
async def overview_charts(request: Request, filters: FilterParams = Depends()):
    """Chart data: volume trend, backlog trend, aging buckets, workload balance."""
    db = request.app.state.db
    conn = await db.get_connection()
    now = _now_tz()

    extra_sql, extra_params = _build_filter_sql(filters)
    extra_and = f" AND {extra_sql}" if extra_sql else ""

    # Volume trend: tickets created per day, last 30 days
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    volume = await conn.execute_fetchall(
        f"""SELECT DATE(created_time) as day, COUNT(*) as count
           FROM tickets WHERE created_time >= ?{extra_and}
           GROUP BY DATE(created_time) ORDER BY day""",
        [thirty_days_ago, *extra_params],
    )
    volume_trend = [{"date": r["day"], "count": r["count"]} for r in volume]

    # Backlog trend: opened, closed, and open snapshot per week (last 12 weeks)
    backlog_trend = []
    for i in range(12, -1, -1):
        week_end = now - timedelta(weeks=i)
        week_start = week_end - timedelta(weeks=1)
        we_iso = week_end.isoformat()
        ws_iso = week_start.isoformat()
        week_label = week_end.strftime("%Y-W%W")

        opened_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE created_time >= ? AND created_time < ?{extra_and}",
            [ws_iso, we_iso, *extra_params],
        )
        closed_row = await conn.execute_fetchall(
            f"SELECT COUNT(*) FROM tickets WHERE resolution_time >= ? AND resolution_time < ?{extra_and}",
            [ws_iso, we_iso, *extra_params],
        )
        # Snapshot: tickets open at week_end
        # A ticket is open if: created before week_end AND (not resolved/closed, OR resolved after week_end)
        # Tickets with NULL resolution_time but status Resolved/Closed are old imports, exclude them
        open_row = await conn.execute_fetchall(
            f"""SELECT COUNT(*) FROM tickets
                WHERE created_time < ?
                AND (
                    (resolution_time IS NOT NULL AND resolution_time >= ?)
                    OR (resolution_time IS NULL AND status NOT IN {CLOSED_STATUSES_SQL})
                ){extra_and}""",
            [we_iso, we_iso, *extra_params],
        )
        backlog_trend.append({
            "week": week_label,
            "opened": opened_row[0][0],
            "closed": closed_row[0][0],
            "open_count": open_row[0][0],
        })

    # Aging buckets: open tickets by age
    aging_buckets = {"0-1d": 0, "1-3d": 0, "3-7d": 0, "7-14d": 0, "14d+": 0}
    open_tickets = await conn.execute_fetchall(
        f"SELECT created_time FROM tickets WHERE status IN {OPEN_STATUSES_SQL}{extra_and}",
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
            WHERE status IN {OPEN_STATUSES_SQL}{extra_and}
            GROUP BY status ORDER BY count DESC""",
        extra_params,
    )
    status_chart = [{"status": r["status"], "count": r["count"]} for r in status_dist]

    # Priority distribution
    priority_dist = await conn.execute_fetchall(
        f"""SELECT priority, COUNT(*) as count FROM tickets
            WHERE status IN {OPEN_STATUSES_SQL}{extra_and}
            GROUP BY priority ORDER BY count DESC""",
        extra_params,
    )
    priority_chart = [{"priority": r["priority"], "count": r["count"]} for r in priority_dist]

    # Workload balance: open tickets per tech
    workload = await conn.execute_fetchall(
        f"""SELECT COALESCE(technician_name, 'Unassigned') as tech, COUNT(*) as count
            FROM tickets WHERE status IN {OPEN_STATUSES_SQL}{extra_and}
            GROUP BY technician_name ORDER BY count DESC""",
        extra_params,
    )
    workload_chart = [{"technician": r["tech"], "count": r["count"]} for r in workload]

    # Tickets by tech group (open tickets); null group treated as Tier 1 Support
    group_dist = await conn.execute_fetchall(
        f"""SELECT COALESCE(tech_group_name, 'Tier 1 Support') as group_name, COUNT(*) as count
            FROM tickets WHERE status IN {OPEN_STATUSES_SQL}{extra_and}
            GROUP BY group_name ORDER BY count DESC""",
        extra_params,
    )
    group_chart = [{"group": r["group_name"], "count": r["count"]} for r in group_dist]

    return {
        "volume_trend": volume_trend,
        "backlog_trend": backlog_trend,
        "aging_buckets": [{"bucket": k, "count": v} for k, v in aging_buckets.items()],
        "status_distribution": status_chart,
        "priority_distribution": priority_chart,
        "workload_balance": workload_chart,
        "group_distribution": group_chart,
    }
