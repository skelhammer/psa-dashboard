"""Phone Analytics API: call volume, agent performance, queue metrics."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.queries import CLOSED_STATUSES_SQL

router = APIRouter(prefix="/api/phone", tags=["phone"])


@router.get("/overview")
async def phone_overview(request: Request, days: int = 30):
    """KPI cards: total calls, answer rate, avg wait, avg handle time."""
    db = request.app.state.db
    conn = await db.get_connection()

    rows = await conn.execute_fetchall(
        """SELECT
            COUNT(*) as total_calls,
            SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) as outbound,
            SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN result = 'missed' THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN result = 'voicemail' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN result = 'abandoned' THEN 1 ELSE 0 END) as abandoned,
            AVG(CASE WHEN result = 'connected' THEN duration ELSE NULL END) as avg_handle,
            AVG(CASE WHEN direction = 'inbound' AND wait_time > 0 THEN wait_time ELSE NULL END) as avg_wait,
            SUM(CASE WHEN result = 'connected' THEN duration ELSE 0 END) as total_talk
        FROM phone_calls
        WHERE start_time >= datetime('now', ? || ' days')""",
        (f"-{days}",),
    )

    r = rows[0] if rows else None
    if not r or r[0] == 0:
        return {
            "total_calls": 0, "inbound": 0, "outbound": 0,
            "answer_rate": 0, "avg_handle_seconds": 0, "avg_wait_seconds": 0,
            "abandoned_rate": 0, "missed": 0, "voicemail": 0, "abandoned": 0,
            "total_talk_hours": 0, "service_level": 0,
        }

    total = r[0] or 1
    inbound = r[1] or 0
    answered = r[3] or 0
    abandoned = r[6] or 0

    # Service level: % of inbound calls answered within 20 seconds
    sl_rows = await conn.execute_fetchall(
        """SELECT COUNT(*) FROM phone_calls
           WHERE direction = 'inbound' AND result = 'connected'
           AND wait_time <= 20
           AND start_time >= datetime('now', ? || ' days')""",
        (f"-{days}",),
    )
    sl_answered_20 = sl_rows[0][0] if sl_rows else 0
    service_level = round((sl_answered_20 / inbound * 100) if inbound > 0 else 0, 1)

    return {
        "total_calls": total,
        "inbound": inbound,
        "outbound": r[2] or 0,
        "answer_rate": round((answered / inbound * 100) if inbound > 0 else 0, 1),
        "avg_handle_seconds": round(r[7] or 0),
        "avg_wait_seconds": round(r[8] or 0),
        "abandoned_rate": round((abandoned / inbound * 100) if inbound > 0 else 0, 1),
        "missed": r[4] or 0,
        "voicemail": r[5] or 0,
        "abandoned": abandoned,
        "total_talk_hours": round((r[9] or 0) / 3600, 1),
        "service_level": service_level,
    }


@router.get("/charts")
async def phone_charts(request: Request, days: int = 30):
    """Chart data: volume by hour, daily trend, outcome distribution."""
    db = request.app.state.db
    conn = await db.get_connection()

    cutoff = f"-{days}"

    # Volume by hour of day
    hourly = await conn.execute_fetchall(
        """SELECT
            CAST(strftime('%H', start_time) AS INTEGER) as hour,
            SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) as connected,
            SUM(CASE WHEN result = 'missed' THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN result = 'voicemail' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN result = 'abandoned' THEN 1 ELSE 0 END) as abandoned
        FROM phone_calls
        WHERE start_time >= datetime('now', ? || ' days')
        GROUP BY hour ORDER BY hour""",
        (cutoff,),
    )
    volume_by_hour = [
        {
            "hour": r[0],
            "label": f"{r[0]}:00",
            "connected": r[1] or 0,
            "missed": r[2] or 0,
            "voicemail": r[3] or 0,
            "abandoned": r[4] or 0,
        }
        for r in hourly
    ]

    # Daily trend
    daily = await conn.execute_fetchall(
        """SELECT
            DATE(start_time) as date,
            COUNT(*) as total,
            SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) as outbound,
            SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) as answered
        FROM phone_calls
        WHERE start_time >= datetime('now', ? || ' days')
        GROUP BY DATE(start_time) ORDER BY date""",
        (cutoff,),
    )
    daily_trend = [
        {
            "date": r[0],
            "total": r[1] or 0,
            "inbound": r[2] or 0,
            "outbound": r[3] or 0,
            "answered": r[4] or 0,
        }
        for r in daily
    ]

    # Outcome distribution
    outcomes = await conn.execute_fetchall(
        """SELECT result, COUNT(*) as count
        FROM phone_calls
        WHERE start_time >= datetime('now', ? || ' days')
        GROUP BY result""",
        (cutoff,),
    )
    outcome_dist = [{"name": r[0], "value": r[1]} for r in outcomes]

    # Heatmap: day-of-week x hour-of-day
    heatmap_rows = await conn.execute_fetchall(
        """SELECT
            CAST(strftime('%w', start_time) AS INTEGER) as dow,
            CAST(strftime('%H', start_time) AS INTEGER) as hour,
            COUNT(*) as count
        FROM phone_calls
        WHERE start_time >= datetime('now', ? || ' days')
        GROUP BY dow, hour""",
        (cutoff,),
    )
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    heatmap = [
        {"day": day_names[r[0]], "day_num": r[0], "hour": r[1], "count": r[2]}
        for r in heatmap_rows
    ]

    return {
        "volume_by_hour": volume_by_hour,
        "daily_trend": daily_trend,
        "outcome_distribution": outcome_dist,
        "heatmap": heatmap,
    }


@router.get("/agents")
async def phone_agents(request: Request, days: int = 30):
    """Per-agent call stats table."""
    db = request.app.state.db
    conn = await db.get_connection()

    rows = await conn.execute_fetchall(
        """SELECT
            pu.id, pu.name, pu.extension, pu.department,
            COALESCE(SUM(pad.total_calls), 0) as total_calls,
            COALESCE(SUM(pad.inbound_calls), 0) as inbound,
            COALESCE(SUM(pad.outbound_calls), 0) as outbound,
            COALESCE(SUM(pad.answered_calls), 0) as answered,
            COALESCE(SUM(pad.missed_calls), 0) as missed,
            COALESCE(SUM(pad.voicemail_calls), 0) as voicemail,
            COALESCE(SUM(pad.total_talk_seconds), 0) as talk_seconds,
            CASE
                WHEN SUM(pad.answered_calls) > 0
                THEN SUM(pad.total_talk_seconds) / SUM(pad.answered_calls)
                ELSE 0
            END as avg_handle
        FROM phone_users pu
        LEFT JOIN phone_agent_daily pad
            ON pu.id = pad.user_id
            AND pad.date >= date('now', ? || ' days')
        GROUP BY pu.id
        ORDER BY total_calls DESC""",
        (f"-{days}",),
    )

    agents = []
    for r in rows:
        inbound = r[5] or 1
        answered = r[7] or 0
        agents.append({
            "id": r[0],
            "name": r[1],
            "extension": r[2],
            "department": r[3],
            "total_calls": r[4],
            "inbound": r[5],
            "outbound": r[6],
            "answered": answered,
            "missed": r[8],
            "voicemail": r[9],
            "talk_hours": round(r[10] / 3600, 1),
            "avg_handle_seconds": round(r[11]),
            "answer_rate": round((answered / inbound * 100) if inbound > 0 else 0, 1),
        })

    return {"agents": agents}


@router.get("/queues")
async def phone_queues(request: Request, days: int = 30):
    """Queue performance table."""
    db = request.app.state.db
    conn = await db.get_connection()

    rows = await conn.execute_fetchall(
        """SELECT
            pq.id, pq.name, pq.extension, pq.member_count,
            COUNT(pc.id) as offered,
            SUM(CASE WHEN pc.result = 'connected' THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN pc.result = 'abandoned' THEN 1 ELSE 0 END) as abandoned,
            AVG(pc.wait_time) as avg_wait,
            AVG(CASE WHEN pc.result = 'connected' THEN pc.duration ELSE NULL END) as avg_handle,
            SUM(CASE WHEN pc.result = 'connected' AND pc.wait_time <= 20 THEN 1 ELSE 0 END) as answered_20
        FROM phone_queues pq
        LEFT JOIN phone_calls pc
            ON pq.id = pc.queue_id
            AND pc.start_time >= datetime('now', ? || ' days')
        GROUP BY pq.id
        ORDER BY offered DESC""",
        (f"-{days}",),
    )

    queues = []
    for r in rows:
        offered = r[4] or 0
        answered = r[5] or 0
        queues.append({
            "id": r[0],
            "name": r[1],
            "extension": r[2],
            "member_count": r[3],
            "offered": offered,
            "answered": answered,
            "abandoned": r[6] or 0,
            "avg_wait_seconds": round(r[7] or 0),
            "avg_handle_seconds": round(r[8] or 0),
            "answer_rate": round((answered / offered * 100) if offered > 0 else 0, 1),
            "service_level": round(((r[9] or 0) / offered * 100) if offered > 0 else 0, 1),
        })

    return {"queues": queues}
