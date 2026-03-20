"""Rule-based insight and alert engine.

Generates alerts by evaluating simple rules against current dashboard data.
Designed to be run after each sync cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)


async def generate_insights(conn: aiosqlite.Connection) -> list[dict]:
    """Generate auto-insights from current data. Returns max 5 most relevant."""
    insights = []
    now = datetime.now()
    settings = get_settings()
    closed_statuses = settings.server.closed_statuses
    closed_sql = "(" + ", ".join(f"'{s}'" for s in closed_statuses) + ")"

    # 1. Client volume spike: any client with 3x their 30-day average in last 7 days
    try:
        spikes = await conn.execute_fetchall("""
            SELECT client_name,
                   COUNT(*) as recent_count,
                   (SELECT COUNT(*) FROM tickets t2
                    WHERE t2.client_id = t.client_id
                    AND t2.created_time >= datetime('now', '-30 days')) / 4.0 as weekly_avg
            FROM tickets t
            WHERE created_time >= datetime('now', '-7 days')
            GROUP BY client_id
            HAVING recent_count > 3 AND recent_count > weekly_avg * 2
            ORDER BY recent_count DESC
            LIMIT 3
        """)
        for row in spikes:
            avg = round(row[2], 1)
            insights.append({
                "type": "warning",
                "title": f"{row[0]}: volume spike",
                "description": f"{row[0]} submitted {row[1]} tickets this week, vs {avg} weekly average.",
                "entity_type": "client",
            })
    except Exception as e:
        logger.warning("Insight rule 'client_spike' failed: %s", e)

    # 2. Tech with no closed tickets in 3+ business days (only for role=technician)
    try:
        idle_techs = await conn.execute_fetchall(f"""
            SELECT t.first_name || ' ' || t.last_name as name,
                   MAX(tk.resolution_time) as last_close
            FROM technicians t
            LEFT JOIN tickets tk ON tk.technician_id = t.id
                AND tk.status IN {closed_sql}
            WHERE COALESCE(t.dashboard_role, 'technician') LIKE '%technician%'
            GROUP BY t.id
            HAVING last_close IS NULL OR last_close < datetime('now', '-3 days')
        """)
        for row in idle_techs:
            last_close = row[1]
            if last_close:
                insights.append({
                    "type": "warning",
                    "title": f"{row[0]}: no closures",
                    "description": f"{row[0]} has not closed a ticket since {last_close[:10]}.",
                    "entity_type": "technician",
                })
            else:
                insights.append({
                    "type": "info",
                    "title": f"{row[0]}: no closures on record",
                    "description": f"{row[0]} has no closed tickets in the current dataset.",
                    "entity_type": "technician",
                })
    except Exception as e:
        logger.warning("Insight rule 'idle_tech' failed: %s", e)

    # 3. Backlog growth: 5+ consecutive days of net-positive tickets
    try:
        daily_net = await conn.execute_fetchall(f"""
            SELECT DATE(created_time) as day,
                   COUNT(*) as created,
                   (SELECT COUNT(*) FROM tickets t2
                    WHERE DATE(t2.resolution_time) = DATE(t.created_time)
                    AND t2.status IN {closed_sql}) as closed
            FROM tickets t
            WHERE created_time >= datetime('now', '-7 days')
            GROUP BY day
            ORDER BY day
        """)
        consecutive_growth = 0
        for row in daily_net:
            if (row[1] or 0) > (row[2] or 0):
                consecutive_growth += 1
            else:
                consecutive_growth = 0

        if consecutive_growth >= 5:
            insights.append({
                "type": "critical",
                "title": "Backlog growing",
                "description": f"Backlog has grown for {consecutive_growth} consecutive days. More tickets created than closed.",
                "entity_type": "system",
            })
        elif consecutive_growth >= 3:
            insights.append({
                "type": "warning",
                "title": "Backlog trend",
                "description": f"Backlog has grown for {consecutive_growth} consecutive days.",
                "entity_type": "system",
            })
    except Exception as e:
        logger.warning("Insight rule 'backlog_growth' failed: %s", e)

    # 4. SLA breach on high-value or high-priority tickets
    try:
        sla_breaches = await conn.execute_fetchall(f"""
            SELECT display_id, subject, client_name, priority
            FROM tickets
            WHERE status NOT IN {closed_sql}
            AND (first_response_violated = 1 OR resolution_violated = 1)
            AND priority IN ('Critical', 'High')
            ORDER BY
                CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END
            LIMIT 3
        """)
        for row in sla_breaches:
            insights.append({
                "type": "critical",
                "title": f"SLA breach: {row[0]}",
                "description": f"{row[3]} priority ticket for {row[2]}: {row[1]}",
                "entity_type": "ticket",
            })
    except Exception as e:
        logger.warning("Insight rule 'sla_breach' failed: %s", e)

    # 5. Unresolved billing flags
    try:
        flag_count = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
        )
        count = flag_count[0][0] if flag_count else 0
        if count > 0:
            insights.append({
                "type": "warning" if count <= 5 else "critical",
                "title": f"{count} billing flag{'s' if count != 1 else ''}",
                "description": f"{count} unresolved billing discrepancies need attention.",
                "entity_type": "billing",
            })
    except Exception as e:
        logger.warning("Insight rule 'billing_flags' failed: %s", e)

    # Sort: critical first, then warning, then info. Limit to 5.
    priority_order = {"critical": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda x: priority_order.get(x["type"], 9))
    return insights[:5]


async def compute_health_summary(conn: aiosqlite.Connection) -> dict:
    """Compute overall service desk health for CEO summary."""
    settings = get_settings()
    closed_statuses = settings.server.closed_statuses
    closed_sql = "(" + ", ".join(f"'{s}'" for s in closed_statuses) + ")"

    # SLA compliance this month
    sla_total = await conn.execute_fetchall(
        """SELECT COUNT(*) FROM tickets
           WHERE created_time >= datetime('now', 'start of month')
           AND sla_name IS NOT NULL"""
    )
    sla_violated = await conn.execute_fetchall(
        """SELECT COUNT(*) FROM tickets
           WHERE created_time >= datetime('now', 'start of month')
           AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1)"""
    )
    total_s = sla_total[0][0] or 0
    violated_s = sla_violated[0][0] or 0
    sla_pct = round(((total_s - violated_s) / total_s * 100) if total_s > 0 else 100, 1)

    # Open backlog
    backlog = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {closed_sql}"
    )
    open_backlog = backlog[0][0] or 0

    # Closed this month vs last month
    closed_this = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', 'start of month')"""
    )
    closed_last = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', 'start of month', '-1 month')
            AND resolution_time < datetime('now', 'start of month')"""
    )
    this_count = closed_this[0][0] or 0
    last_count = closed_last[0][0] or 1
    close_change_pct = round((this_count - last_count) / max(last_count, 1) * 100)

    # Billing flags
    flags = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
    )
    billing_flags = flags[0][0] or 0

    # Backlog clearance estimate (days at current close rate)
    avg_daily_close = await conn.execute_fetchall(
        f"""SELECT COUNT(*) * 1.0 / MAX(1, JULIANDAY('now') - JULIANDAY(MIN(resolution_time)))
            FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', '-30 days')"""
    )
    daily_rate = avg_daily_close[0][0] or 1
    clearance_days = round(open_backlog / max(daily_rate, 0.1), 1)

    # Determine overall health: green, yellow, red
    if sla_pct >= 95 and open_backlog <= 20 and billing_flags <= 2:
        health = "green"
        summary_text = (
            f"Service desk is running well. "
            f"SLA at {sla_pct}%, team closed {abs(close_change_pct)}% "
            f"{'more' if close_change_pct >= 0 else 'fewer'} tickets than last month."
        )
    elif sla_pct >= 80 and open_backlog <= 40:
        health = "yellow"
        summary_text = (
            f"Service desk needs attention. "
            f"SLA at {sla_pct}%, backlog at {open_backlog} tickets "
            f"(clears in ~{clearance_days} days at current rate)."
        )
    else:
        health = "red"
        summary_text = (
            f"Service desk performance is below target. "
            f"SLA at {sla_pct}%, backlog at {open_backlog} tickets."
        )

    if billing_flags > 0:
        summary_text += f" {billing_flags} billing flag{'s' if billing_flags != 1 else ''} need attention."

    return {
        "health": health,
        "summary": summary_text,
        "sla_pct": sla_pct,
        "open_backlog": open_backlog,
        "clearance_days": clearance_days,
        "close_change_pct": close_change_pct,
        "billing_flags": billing_flags,
    }
