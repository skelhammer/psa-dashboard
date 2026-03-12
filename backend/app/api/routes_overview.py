"""Overview / Home API: KPI cards and chart data."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import FilterParams, build_where_clause
from app.api.queries import CLOSED_STATUSES_SQL, OPEN_STATUSES_SQL

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview")
async def overview(request: Request, filters: FilterParams = Depends()):
    db = request.app.state.db
    conn = await db.get_connection()

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)
    year_start = today_start.replace(month=1, day=1)

    where, params = build_where_clause(filters)

    # Total open tickets
    open_count = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {OPEN_STATUSES_SQL}"
    )

    # Tickets created in various periods
    created_today = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE created_time >= ?", (today_start.isoformat(),)
    )
    created_week = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE created_time >= ?", (week_start.isoformat(),)
    )
    created_month = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE created_time >= ?", (month_start.isoformat(),)
    )
    created_year = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE created_time >= ?", (year_start.isoformat(),)
    )

    # Closed this week
    closed_week = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status IN {CLOSED_STATUSES_SQL} AND resolution_time >= ?",
        (week_start.isoformat(),),
    )

    # Average first response time (this month, in minutes)
    avg_fr = await conn.execute_fetchall(
        """SELECT AVG(
            (julianday(first_response_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE first_response_time IS NOT NULL AND created_time >= ?""",
        (month_start.isoformat(),),
    )

    # Average resolution time (this month, in minutes)
    avg_res = await conn.execute_fetchall(
        """SELECT AVG(
            (julianday(resolution_time) - julianday(created_time)) * 24 * 60
        ) FROM tickets
        WHERE resolution_time IS NOT NULL AND created_time >= ?""",
        (month_start.isoformat(),),
    )

    # SLA compliance rate (this month)
    total_with_sla = await conn.execute_fetchall(
        """SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND sla_name IS NOT NULL""",
        (month_start.isoformat(),),
    )
    violated_sla = await conn.execute_fetchall(
        """SELECT COUNT(*) FROM tickets
           WHERE created_time >= ? AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1)""",
        (month_start.isoformat(),),
    )

    total_sla = total_with_sla[0][0] or 0
    violated = violated_sla[0][0] or 0
    sla_compliance = round(((total_sla - violated) / total_sla * 100) if total_sla > 0 else 100, 1)

    # FCR rate (this month: resolved with 1 tech reply, within 4 hours)
    fcr_eligible = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL}
            AND created_time >= ?""",
        (month_start.isoformat(),),
    )
    fcr_count = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {CLOSED_STATUSES_SQL}
            AND created_time >= ?
            AND tech_reply_count = 1
            AND (julianday(resolution_time) - julianday(created_time)) * 24 <= 4""",
        (month_start.isoformat(),),
    )
    fcr_total = fcr_eligible[0][0] or 0
    fcr = fcr_count[0][0] or 0
    fcr_rate = round((fcr / fcr_total * 100) if fcr_total > 0 else 0, 1)

    # Total worklog hours (this month)
    worklog = await conn.execute_fetchall(
        "SELECT SUM(worklog_minutes) FROM tickets WHERE created_time >= ?",
        (month_start.isoformat(),),
    )
    total_worklog_hours = round((worklog[0][0] or 0) / 60, 1)

    # Unresolved billing flags
    billing_flags = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
    )

    # Reopened tickets this month
    reopened = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE reopened = 1 AND created_time >= ?",
        (month_start.isoformat(),),
    )

    return {
        "kpis": {
            "total_open": open_count[0][0],
            "created_today": created_today[0][0],
            "created_this_week": created_week[0][0],
            "created_this_month": created_month[0][0],
            "created_this_year": created_year[0][0],
            "closed_this_week": closed_week[0][0],
            "avg_first_response_minutes": round(avg_fr[0][0] or 0, 1),
            "avg_resolution_minutes": round(avg_res[0][0] or 0, 1),
            "sla_compliance_pct": sla_compliance,
            "fcr_rate_pct": fcr_rate,
            "total_worklog_hours": total_worklog_hours,
            "unresolved_billing_flags": billing_flags[0][0],
            "reopened_this_month": reopened[0][0],
            "open_vs_closed_ratio": {
                "opened": created_week[0][0],
                "closed": closed_week[0][0],
            },
        },
    }


@router.get("/overview/charts")
async def overview_charts(request: Request):
    """Chart data: volume trend, backlog trend, aging buckets, workload balance."""
    db = request.app.state.db
    conn = await db.get_connection()
    now = datetime.now()

    # Volume trend: tickets created per day, last 30 days
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    volume = await conn.execute_fetchall(
        """SELECT DATE(created_time) as day, COUNT(*) as count
           FROM tickets WHERE created_time >= ?
           GROUP BY DATE(created_time) ORDER BY day""",
        (thirty_days_ago,),
    )
    volume_trend = [{"date": r["day"], "count": r["count"]} for r in volume]

    # Backlog trend: opened vs closed per week, last 12 weeks
    twelve_weeks_ago = (now - timedelta(weeks=12)).isoformat()
    opened_by_week = await conn.execute_fetchall(
        """SELECT strftime('%Y-W%W', created_time) as week, COUNT(*) as count
           FROM tickets WHERE created_time >= ?
           GROUP BY week ORDER BY week""",
        (twelve_weeks_ago,),
    )
    closed_by_week = await conn.execute_fetchall(
        """SELECT strftime('%Y-W%W', resolution_time) as week, COUNT(*) as count
           FROM tickets WHERE resolution_time IS NOT NULL AND resolution_time >= ?
           GROUP BY week ORDER BY week""",
        (twelve_weeks_ago,),
    )

    opened_map = {r["week"]: r["count"] for r in opened_by_week}
    closed_map = {r["week"]: r["count"] for r in closed_by_week}
    all_weeks = sorted(set(list(opened_map.keys()) + list(closed_map.keys())))
    cumulative = 0
    backlog_trend = []
    for week in all_weeks:
        o = opened_map.get(week, 0)
        c = closed_map.get(week, 0)
        cumulative += o - c
        backlog_trend.append({"week": week, "opened": o, "closed": c, "net_backlog": cumulative})

    # Aging buckets: open tickets by age
    aging_buckets = {"0-1d": 0, "1-3d": 0, "3-7d": 0, "7-14d": 0, "14d+": 0}
    open_tickets = await conn.execute_fetchall(
        f"SELECT created_time FROM tickets WHERE status IN {OPEN_STATUSES_SQL}"
    )
    for row in open_tickets:
        try:
            created = datetime.fromisoformat(row["created_time"])
            age_days = (now - created).total_seconds() / 86400
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
            WHERE status IN {OPEN_STATUSES_SQL}
            GROUP BY status ORDER BY count DESC"""
    )
    status_chart = [{"status": r["status"], "count": r["count"]} for r in status_dist]

    # Priority distribution
    priority_dist = await conn.execute_fetchall(
        f"""SELECT priority, COUNT(*) as count FROM tickets
            WHERE status IN {OPEN_STATUSES_SQL}
            GROUP BY priority ORDER BY count DESC"""
    )
    priority_chart = [{"priority": r["priority"], "count": r["count"]} for r in priority_dist]

    # Workload balance: open tickets per tech
    workload = await conn.execute_fetchall(
        f"""SELECT COALESCE(technician_name, 'Unassigned') as tech, COUNT(*) as count
            FROM tickets WHERE status IN {OPEN_STATUSES_SQL}
            GROUP BY technician_name ORDER BY count DESC"""
    )
    workload_chart = [{"technician": r["tech"], "count": r["count"]} for r in workload]

    return {
        "volume_trend": volume_trend,
        "backlog_trend": backlog_trend,
        "aging_buckets": [{"bucket": k, "count": v} for k, v in aging_buckets.items()],
        "status_distribution": status_chart,
        "priority_distribution": priority_chart,
        "workload_balance": workload_chart,
    }
