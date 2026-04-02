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
    consecutive_growth = 0
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

    # 6. Phone answer rate drop (> 5% decline vs prior period)
    try:
        current_phone = await conn.execute_fetchall("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN direction = 'inbound' AND result = 'connected' THEN 1 ELSE 0 END) as answered,
                   SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound
            FROM phone_calls
            WHERE start_time >= datetime('now', '-7 days') AND is_internal = 0
        """)
        prior_phone = await conn.execute_fetchall("""
            SELECT SUM(CASE WHEN direction = 'inbound' AND result = 'connected' THEN 1 ELSE 0 END) as answered,
                   SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound
            FROM phone_calls
            WHERE start_time >= datetime('now', '-14 days') AND start_time < datetime('now', '-7 days') AND is_internal = 0
        """)
        cur_inbound = current_phone[0][2] or 0
        cur_answered = current_phone[0][1] or 0
        prior_inbound = prior_phone[0][1] or 0
        prior_answered = prior_phone[0][0] or 0
        if cur_inbound > 10 and prior_inbound > 10:
            cur_rate = cur_answered / cur_inbound * 100
            prior_rate = prior_answered / prior_inbound * 100
            drop = prior_rate - cur_rate
            if drop > 5:
                insights.append({
                    "type": "warning" if drop <= 10 else "critical",
                    "title": "Phone answer rate declining",
                    "description": f"Answer rate dropped {round(drop, 1)}% this week ({round(cur_rate, 1)}% vs {round(prior_rate, 1)}% prior week).",
                    "entity_type": "system",
                })
    except Exception as e:
        logger.warning("Insight rule 'phone_answer_rate' failed: %s", e)

    # 7. Capacity alert (utilization > 90% AND backlog growing)
    try:
        tech_rows = await conn.execute_fetchall(
            "SELECT available_hours_per_week FROM technicians WHERE COALESCE(dashboard_role, 'technician') LIKE '%technician%'"
        )
        if tech_rows:
            weeks = 2
            total_avail = sum((t[0] or 40) * weeks for t in tech_rows)
            worked_row = await conn.execute_fetchall(
                "SELECT SUM(worklog_hours) FROM tickets WHERE created_time >= datetime('now', '-14 days')"
            )
            worked = worked_row[0][0] or 0
            util_pct = (worked / total_avail * 100) if total_avail > 0 else 0
            if util_pct > 90 and consecutive_growth >= 3:
                insights.append({
                    "type": "critical",
                    "title": "Capacity strain",
                    "description": f"Team utilization at {round(util_pct)}% with backlog growing {consecutive_growth} consecutive days. Consider additional staffing.",
                    "entity_type": "system",
                })
    except Exception as e:
        logger.warning("Insight rule 'capacity_alert' failed: %s", e)

    # 8. FCR decline (> 10% drop vs prior period)
    try:
        fcr_current = await conn.execute_fetchall(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN fcr = 1 THEN 1 ELSE 0 END) as resolved
            FROM tickets
            WHERE status IN {closed_sql} AND resolution_time >= datetime('now', '-14 days')
        """)
        fcr_prior = await conn.execute_fetchall(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN fcr = 1 THEN 1 ELSE 0 END) as resolved
            FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', '-28 days') AND resolution_time < datetime('now', '-14 days')
        """)
        cur_fcr_total = fcr_current[0][0] or 0
        cur_fcr_yes = fcr_current[0][1] or 0
        prior_fcr_total = fcr_prior[0][0] or 0
        prior_fcr_yes = fcr_prior[0][1] or 0
        if cur_fcr_total > 10 and prior_fcr_total > 10:
            cur_fcr_rate = cur_fcr_yes / cur_fcr_total * 100
            prior_fcr_rate = prior_fcr_yes / prior_fcr_total * 100
            fcr_drop = prior_fcr_rate - cur_fcr_rate
            if fcr_drop > 10:
                insights.append({
                    "type": "warning",
                    "title": "FCR rate declining",
                    "description": f"First call resolution dropped {round(fcr_drop, 1)}% ({round(cur_fcr_rate, 1)}% vs {round(prior_fcr_rate, 1)}% prior period).",
                    "entity_type": "system",
                })
    except Exception as e:
        logger.warning("Insight rule 'fcr_decline' failed: %s", e)

    # 9. Client churn risk (declining volume + contract expiring within 90 days)
    try:
        at_risk = await conn.execute_fetchall("""
            SELECT c.name, cc.end_date,
                   (SELECT COUNT(*) FROM tickets t WHERE t.client_id = c.id
                    AND t.created_time >= datetime('now', '-30 days')) as recent_count,
                   (SELECT COUNT(*) FROM tickets t WHERE t.client_id = c.id
                    AND t.created_time >= datetime('now', '-60 days')
                    AND t.created_time < datetime('now', '-30 days')) as prior_count
            FROM clients c
            JOIN client_contracts cc ON cc.client_id = c.id
            WHERE cc.end_date IS NOT NULL
              AND cc.end_date <= datetime('now', '+90 days')
              AND cc.end_date > datetime('now')
              AND cc.status = 'Active'
            ORDER BY cc.end_date ASC
            LIMIT 3
        """)
        for row in at_risk:
            recent = row[2] or 0
            prior = row[3] or 0
            if prior > 5 and recent < prior * 0.7:
                insights.append({
                    "type": "warning",
                    "title": f"{row[0]}: renewal risk",
                    "description": f"Contract expires {row[1][:10]} and ticket volume dropped {round((1 - recent / prior) * 100)}%.",
                    "entity_type": "client",
                })
    except Exception as e:
        logger.warning("Insight rule 'churn_risk' failed: %s", e)

    # Sort: critical first, then warning, then info. Limit to 5.
    priority_order = {"critical": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda x: priority_order.get(x["type"], 9))
    return insights[:5]


async def compute_health_summary(
    conn: aiosqlite.Connection,
    extra_sql: str = "",
    extra_params: list | None = None,
) -> dict:
    """Compute overall service desk health for CEO summary.

    Accepts optional filter SQL so the health summary respects active filters.
    """
    settings = get_settings()
    closed_statuses = settings.server.closed_statuses
    closed_sql = "(" + ", ".join(f"'{s}'" for s in closed_statuses) + ")"
    ep = extra_params or []
    extra = f" AND {extra_sql}" if extra_sql else ""

    # SLA compliance this month
    sla_total = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= datetime('now', 'start of month')
           AND sla_name IS NOT NULL{extra}""",
        ep,
    )
    sla_violated = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
           WHERE created_time >= datetime('now', 'start of month')
           AND sla_name IS NOT NULL
           AND (first_response_violated = 1 OR resolution_violated = 1){extra}""",
        ep,
    )
    total_s = sla_total[0][0] or 0
    violated_s = sla_violated[0][0] or 0
    sla_pct = round(((total_s - violated_s) / total_s * 100) if total_s > 0 else 100, 1)

    # Open backlog
    backlog = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {closed_sql}{extra}",
        ep,
    )
    open_backlog = backlog[0][0] or 0

    # Closed this month vs last month
    closed_this = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', 'start of month'){extra}""",
        ep,
    )
    closed_last = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status IN {closed_sql}
            AND resolution_time >= datetime('now', 'start of month', '-1 month')
            AND resolution_time < datetime('now', 'start of month'){extra}""",
        ep,
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
            AND resolution_time >= datetime('now', '-30 days'){extra}""",
        ep,
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
