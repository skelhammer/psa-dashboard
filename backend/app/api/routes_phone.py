"""Phone Analytics API: call volume, agent performance, queue metrics."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import FilterParams
from app.api.queries import CLOSED_STATUSES_SQL

router = APIRouter(prefix="/api/phone", tags=["phone"])


def _phone_date_clause(
    filters: FilterParams,
    col: str = "start_time",
    prefix: str = "",
    exclude_internal: bool = False,
) -> tuple[str, list]:
    """Build a date WHERE clause for phone_calls using FilterParams dates."""
    full_col = f"{prefix}.{col}" if prefix else col
    clause = f"{full_col} >= ? AND {full_col} <= ?"
    params: list = [filters.date_from.isoformat(), filters.date_to.isoformat()]
    if exclude_internal:
        int_col = f"{prefix}.is_internal" if prefix else "is_internal"
        clause += f" AND {int_col} = 0"
    return clause, params


def _prior_period_dates(
    date_from: date, date_to: date
) -> tuple[date, date]:
    """Compute the equivalent prior period for comparison."""
    span = (date_to - date_from).days + 1
    prior_to = date_from - timedelta(days=1)
    prior_from = prior_to - timedelta(days=span - 1)
    return prior_from, prior_to


def _pct_change(current: float, prior: float) -> float:
    if prior == 0:
        return 0.0
    return round((current - prior) / prior * 100, 1)


async def _run_overview_query(conn, date_clause: str, date_params: list):
    """Shared overview query used for current and prior period."""
    rows = await conn.execute_fetchall(
        f"""SELECT
            COUNT(*) as total_calls,
            SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) as outbound,
            SUM(CASE WHEN direction = 'inbound' AND result = 'connected' THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN result = 'missed' THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN result = 'voicemail' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN result = 'abandoned' THEN 1 ELSE 0 END) as abandoned,
            AVG(CASE WHEN result = 'connected' THEN duration ELSE NULL END) as avg_handle,
            AVG(CASE WHEN direction = 'inbound' AND wait_time > 0 THEN wait_time ELSE NULL END) as avg_wait,
            SUM(CASE WHEN result = 'connected' THEN duration ELSE 0 END) as total_talk,
            AVG(CASE WHEN hold_time > 0 THEN hold_time ELSE NULL END) as avg_hold
        FROM phone_calls
        WHERE {date_clause}""",
        date_params,
    )
    r = rows[0] if rows else None
    if not r or r[0] == 0:
        return None
    # Service level
    sl_rows = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM phone_calls
           WHERE direction = 'inbound' AND result = 'connected'
           AND wait_time <= 20
           AND {date_clause}""",
        date_params,
    )
    sl_answered_20 = sl_rows[0][0] if sl_rows else 0
    inbound = r[1] or 0
    answered = r[3] or 0
    abandoned = r[6] or 0
    return {
        "total_calls": r[0],
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
        "avg_hold_seconds": round(r[10] or 0),
        "service_level": round((sl_answered_20 / inbound * 100) if inbound > 0 else 0, 1),
    }


@router.get("/overview")
async def phone_overview(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """KPI cards: total calls, answer rate, avg wait, avg handle, hold, comparison."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )
    current = await _run_overview_query(conn, date_clause, date_params)

    empty = {
        "total_calls": 0, "inbound": 0, "outbound": 0,
        "answer_rate": 0, "avg_handle_seconds": 0, "avg_wait_seconds": 0,
        "avg_hold_seconds": 0,
        "abandoned_rate": 0, "missed": 0, "voicemail": 0, "abandoned": 0,
        "total_talk_hours": 0, "service_level": 0,
        "date_range_label": filters.date_range_label,
        "comparison": None,
    }
    if current is None:
        return empty

    # Prior period comparison
    prior_from, prior_to = _prior_period_dates(filters.date_from, filters.date_to)
    prior_filters = SimpleNamespace(date_from=prior_from, date_to=prior_to)
    prior_clause, prior_params = _phone_date_clause(
        prior_filters, exclude_internal=exclude_internal
    )
    prior = await _run_overview_query(conn, prior_clause, prior_params)

    comparison = None
    if prior:
        comparison = {
            "total_calls_pct": _pct_change(current["total_calls"], prior["total_calls"]),
            "answer_rate_pct": round(current["answer_rate"] - prior["answer_rate"], 1),
            "avg_wait_pct": _pct_change(current["avg_wait_seconds"], prior["avg_wait_seconds"]),
            "avg_handle_pct": _pct_change(current["avg_handle_seconds"], prior["avg_handle_seconds"]),
            "abandoned_rate_pct": round(current["abandoned_rate"] - prior["abandoned_rate"], 1),
            "service_level_pct": round(current["service_level"] - prior["service_level"], 1),
            "avg_hold_pct": _pct_change(current["avg_hold_seconds"], prior["avg_hold_seconds"]),
        }

    return {
        **current,
        "date_range_label": filters.date_range_label,
        "comparison": comparison,
    }


@router.get("/charts")
async def phone_charts(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Chart data: volume by hour, daily trend, outcome distribution."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )

    # Volume by hour of day
    hourly = await conn.execute_fetchall(
        f"""SELECT
            CAST(strftime('%H', start_time) AS INTEGER) as hour,
            SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) as connected,
            SUM(CASE WHEN result = 'missed' THEN 1 ELSE 0 END) as missed,
            SUM(CASE WHEN result = 'voicemail' THEN 1 ELSE 0 END) as voicemail,
            SUM(CASE WHEN result = 'abandoned' THEN 1 ELSE 0 END) as abandoned
        FROM phone_calls
        WHERE {date_clause}
        GROUP BY hour ORDER BY hour""",
        date_params,
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
        f"""SELECT
            DATE(start_time) as date,
            COUNT(*) as total,
            SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END) as inbound,
            SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) as outbound,
            SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) as answered
        FROM phone_calls
        WHERE {date_clause}
        GROUP BY DATE(start_time) ORDER BY date""",
        date_params,
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
        f"""SELECT result, COUNT(*) as count
        FROM phone_calls
        WHERE {date_clause}
        GROUP BY result""",
        date_params,
    )
    outcome_dist = [{"name": r[0], "value": r[1]} for r in outcomes]

    # Heatmap: day-of-week x hour-of-day
    heatmap_rows = await conn.execute_fetchall(
        f"""SELECT
            CAST(strftime('%w', start_time) AS INTEGER) as dow,
            CAST(strftime('%H', start_time) AS INTEGER) as hour,
            COUNT(*) as count
        FROM phone_calls
        WHERE {date_clause}
        GROUP BY dow, hour""",
        date_params,
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
async def phone_agents(request: Request, filters: FilterParams = Depends()):
    """Per-agent call stats table."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_from = filters.date_from.isoformat()
    date_to = filters.date_to.isoformat()

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
            AND pad.date >= date(?)
            AND pad.date <= date(?)
        GROUP BY pu.id
        ORDER BY total_calls DESC""",
        (date_from, date_to),
    )

    agents = []
    for r in rows:
        inbound = r[5] or 0
        missed = r[8] or 0
        voicemail = r[9] or 0
        # Answer rate: inbound calls that were connected vs total inbound.
        # answered_calls includes outbound connected, so derive inbound-answered
        # from inbound - missed - voicemail (calls that were not missed or VM).
        inbound_answered = max(inbound - missed - voicemail, 0)
        agents.append({
            "id": r[0],
            "name": r[1],
            "extension": r[2],
            "department": r[3],
            "total_calls": r[4],
            "inbound": r[5],
            "outbound": r[6],
            "answered": inbound_answered,
            "missed": missed,
            "voicemail": voicemail,
            "talk_hours": round(r[10] / 3600, 1),
            "avg_handle_seconds": round(r[11]),
            "answer_rate": round((inbound_answered / inbound * 100) if inbound > 0 else 0, 1),
        })

    return {"agents": agents}


@router.get("/queues")
async def phone_queues(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Queue performance table."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(
        filters, prefix="pc", exclude_internal=exclude_internal
    )

    rows = await conn.execute_fetchall(
        f"""SELECT
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
            AND {date_clause}
        GROUP BY pq.id
        ORDER BY offered DESC""",
        date_params,
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


@router.get("/metrics/callback-rate")
async def phone_callback_rate(
    request: Request, filters: FilterParams = Depends(), window_hours: int = 4
):
    """Callback rate: repeat callers within a time window."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(filters, col="start_time", prefix="a")

    # Find repeat callers: inbound calls where the same caller_number
    # has another inbound call within window_hours
    repeat_rows = await conn.execute_fetchall(
        f"""SELECT DISTINCT a.caller_number
        FROM phone_calls a
        INNER JOIN phone_calls b
            ON a.caller_number = b.caller_number
            AND a.id != b.id
            AND a.direction = 'inbound'
            AND b.direction = 'inbound'
            AND b.start_time > a.start_time
            AND b.start_time <= datetime(a.start_time, '+' || ? || ' hours')
        WHERE {date_clause}
            AND a.caller_number IS NOT NULL
            AND a.caller_number != ''""",
        [str(window_hours)] + date_params,
    )
    repeat_callers = len(repeat_rows)

    date_clause_plain, date_params_plain = _phone_date_clause(filters)

    # Total unique inbound callers
    unique_rows = await conn.execute_fetchall(
        f"""SELECT COUNT(DISTINCT caller_number) as cnt
        FROM phone_calls
        WHERE direction = 'inbound'
            AND {date_clause_plain}
            AND caller_number IS NOT NULL
            AND caller_number != ''""",
        date_params_plain,
    )
    total_unique = unique_rows[0][0] if unique_rows else 0

    # Top 10 repeat caller numbers
    top_rows = await conn.execute_fetchall(
        f"""SELECT pc.caller_number, pc.caller_name, COUNT(*) as call_count
        FROM phone_calls pc
        WHERE pc.direction = 'inbound'
            AND pc.start_time >= ? AND pc.start_time <= ?
            AND pc.caller_number IS NOT NULL
            AND pc.caller_number != ''
            AND pc.caller_number IN (
                SELECT DISTINCT a.caller_number
                FROM phone_calls a
                INNER JOIN phone_calls b
                    ON a.caller_number = b.caller_number
                    AND a.id != b.id
                    AND a.direction = 'inbound'
                    AND b.direction = 'inbound'
                    AND b.start_time > a.start_time
                    AND b.start_time <= datetime(a.start_time, '+' || ? || ' hours')
                WHERE a.start_time >= ? AND a.start_time <= ?
                    AND a.caller_number IS NOT NULL
                    AND a.caller_number != ''
            )
        GROUP BY pc.caller_number
        ORDER BY call_count DESC
        LIMIT 10""",
        date_params_plain + [str(window_hours)] + date_params_plain,
    )
    top_repeat = [
        {"number": r[0], "name": r[1], "count": r[2]}
        for r in top_rows
    ]

    callback_rate = round((repeat_callers / total_unique * 100) if total_unique > 0 else 0, 1)

    return {
        "callback_rate": callback_rate,
        "repeat_callers": repeat_callers,
        "total_unique_callers": total_unique,
        "top_repeat_numbers": top_repeat,
    }


@router.get("/metrics/peak-hours")
async def phone_peak_hours(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Peak hour analysis with staffing insights."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )

    # Count distinct days in the range for per-day averages
    day_count_rows = await conn.execute_fetchall(
        f"""SELECT COUNT(DISTINCT DATE(start_time)) as day_count
        FROM phone_calls
        WHERE {date_clause}""",
        date_params,
    )
    num_days = day_count_rows[0][0] if day_count_rows and day_count_rows[0][0] > 0 else 1

    # Aggregate calls by hour of day
    hourly_rows = await conn.execute_fetchall(
        f"""SELECT
            CAST(strftime('%H', start_time) AS INTEGER) as hour,
            COUNT(*) as total_calls,
            AVG(CASE WHEN direction = 'inbound' AND wait_time > 0 THEN wait_time ELSE NULL END) as avg_wait,
            AVG(CASE WHEN result = 'connected' THEN duration ELSE NULL END) as avg_handle
        FROM phone_calls
        WHERE {date_clause}
        GROUP BY hour
        ORDER BY hour""",
        date_params,
    )

    hours_data = []
    for r in hourly_rows:
        avg_calls = round(r[1] / num_days, 1)
        hours_data.append({
            "hour": r[0],
            "label": f"{r[0]}:00",
            "avg_calls": avg_calls,
            "avg_wait_seconds": round(r[2] or 0),
            "avg_handle_seconds": round(r[3] or 0),
        })

    # Sort by avg_calls descending for peak, ascending for quiet
    sorted_desc = sorted(hours_data, key=lambda h: h["avg_calls"], reverse=True)
    sorted_asc = sorted(hours_data, key=lambda h: h["avg_calls"])

    peak_hours = sorted_desc[:3]
    quiet_hours = [{"hour": h["hour"], "label": h["label"], "avg_calls": h["avg_calls"]} for h in sorted_asc[:3]]

    total_avg = sum(h["avg_calls"] for h in hours_data)
    overall_avg = round(total_avg / len(hours_data), 1) if hours_data else 0

    return {
        "peak_hours": peak_hours,
        "quiet_hours": quiet_hours,
        "busiest_hour": sorted_desc[0]["hour"] if sorted_desc else 0,
        "quietest_hour": sorted_asc[0]["hour"] if sorted_asc else 0,
        "overall_avg_per_hour": overall_avg,
    }


@router.get("/metrics/voicemail-response")
async def phone_voicemail_response(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Voicemail follow-up response time tracking."""
    db = request.app.state.db
    conn = await db.get_connection()

    date_clause, date_params = _phone_date_clause(
        filters, col="start_time", prefix="vm", exclude_internal=exclude_internal
    )

    # Total voicemails in the period
    date_clause_plain, date_params_plain = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )
    vm_count_rows = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM phone_calls
        WHERE result = 'voicemail'
            AND {date_clause_plain}""",
        date_params_plain,
    )
    total_voicemails = vm_count_rows[0][0] if vm_count_rows else 0

    # For each voicemail, find the next outbound call to the same number within 24h
    response_rows = await conn.execute_fetchall(
        f"""SELECT
            vm.id,
            (julianday(ob.start_time) - julianday(vm.start_time)) * 1440 as response_minutes
        FROM phone_calls vm
        INNER JOIN phone_calls ob
            ON ob.callee_number = vm.caller_number
            AND ob.direction = 'outbound'
            AND ob.start_time > vm.start_time
            AND ob.start_time <= datetime(vm.start_time, '+24 hours')
        WHERE vm.result = 'voicemail'
            AND {date_clause}
            AND vm.caller_number IS NOT NULL
            AND vm.caller_number != ''
        GROUP BY vm.id
        HAVING ob.start_time = MIN(ob.start_time)""",
        date_params,
    )

    responded_count = len(response_rows)
    unresponded_count = total_voicemails - responded_count

    if responded_count > 0:
        avg_minutes = round(sum(r[1] for r in response_rows) / responded_count, 1)
    else:
        avg_minutes = 0

    response_rate = round((responded_count / total_voicemails * 100) if total_voicemails > 0 else 0, 1)

    return {
        "avg_response_minutes": avg_minutes,
        "responded_count": responded_count,
        "unresponded_count": unresponded_count,
        "total_voicemails": total_voicemails,
        "response_rate": response_rate,
    }


@router.get("/metrics/wait-distribution")
async def phone_wait_distribution(
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Wait time distribution bucketed into SLA tiers."""
    db = request.app.state.db
    conn = await db.get_connection()
    date_clause, date_params = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )

    rows = await conn.execute_fetchall(
        f"""SELECT
            CASE
                WHEN wait_time < 10 THEN '< 10s'
                WHEN wait_time < 20 THEN '10-20s'
                WHEN wait_time < 30 THEN '20-30s'
                WHEN wait_time < 60 THEN '30-60s'
                ELSE '60s+'
            END as tier,
            COUNT(*) as cnt,
            queue_name
        FROM phone_calls
        WHERE direction = 'inbound'
            AND result = 'connected'
            AND {date_clause}
        GROUP BY tier, queue_name
        ORDER BY
            CASE tier
                WHEN '< 10s' THEN 1
                WHEN '10-20s' THEN 2
                WHEN '20-30s' THEN 3
                WHEN '30-60s' THEN 4
                ELSE 5
            END""",
        date_params,
    )

    # Aggregate overall tiers
    tier_order = ["< 10s", "10-20s", "20-30s", "30-60s", "60s+"]
    overall: dict[str, int] = {t: 0 for t in tier_order}
    by_queue: dict[str, dict[str, int]] = {}
    for r in rows:
        tier, cnt, qname = r[0], r[1], r[2] or "Direct"
        overall[tier] = overall.get(tier, 0) + cnt
        if qname not in by_queue:
            by_queue[qname] = {t: 0 for t in tier_order}
        by_queue[qname][tier] = by_queue[qname].get(tier, 0) + cnt

    total = sum(overall.values()) or 1
    tiers = [
        {"label": t, "count": overall[t], "pct": round(overall[t] / total * 100, 1)}
        for t in tier_order
    ]

    queue_list = []
    for qname in sorted(by_queue.keys()):
        qt = by_queue[qname]
        q_total = sum(qt.values()) or 1
        queue_list.append({
            "queue_name": qname,
            "tiers": [
                {"label": t, "count": qt[t], "pct": round(qt[t] / q_total * 100, 1)}
                for t in tier_order
            ],
        })

    return {"tiers": tiers, "by_queue": queue_list}


@router.get("/drilldown/{metric}")
async def phone_drilldown(
    metric: str,
    request: Request,
    filters: FilterParams = Depends(),
    exclude_internal: bool = Query(False),
):
    """Drill down into a KPI to see which agents/queues contribute most."""
    db = request.app.state.db
    conn = await db.get_connection()

    valid_metrics = {"answer_rate", "abandoned", "avg_wait", "service_level", "hold_time"}
    if metric not in valid_metrics:
        return {"metric": metric, "error": f"Unknown metric. Valid: {', '.join(sorted(valid_metrics))}"}

    date_from = filters.date_from.isoformat()
    date_to = filters.date_to.isoformat()
    date_clause, date_params = _phone_date_clause(
        filters, exclude_internal=exclude_internal
    )

    if metric in ("answer_rate", "hold_time"):
        # Agent-level drill-down
        rows = await conn.execute_fetchall(
            """SELECT
                pu.name,
                COALESCE(SUM(pad.inbound_calls), 0) as inbound,
                COALESCE(SUM(pad.answered_calls), 0) as answered,
                COALESCE(SUM(pad.missed_calls), 0) as missed,
                COALESCE(SUM(pad.voicemail_calls), 0) as voicemail,
                COALESCE(SUM(pad.total_calls), 0) as total_calls,
                COALESCE(SUM(pad.total_hold_seconds), 0) as hold_secs,
                COALESCE(SUM(pad.answered_calls), 0) as connected_for_hold
            FROM phone_users pu
            LEFT JOIN phone_agent_daily pad
                ON pu.id = pad.user_id
                AND pad.date >= date(?)
                AND pad.date <= date(?)
            GROUP BY pu.id
            HAVING total_calls > 0
            ORDER BY total_calls DESC""",
            (date_from, date_to),
        )

        items = []
        all_values = []
        for r in rows:
            name, inbound, answered, missed, vm, total, hold_secs, connected = (
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
            )
            if metric == "answer_rate":
                inbound_answered = max(inbound - missed - vm, 0)
                val = round((inbound_answered / inbound * 100) if inbound > 0 else 0, 1)
            else:
                val = round(hold_secs / connected) if connected > 0 else 0
            all_values.append(val)
            items.append({"name": name, "type": "agent", "value": val, "total_calls": total})

        team_avg = round(sum(all_values) / len(all_values), 1) if all_values else 0
        for item in items:
            item["gap"] = round(item["value"] - team_avg, 1)

        # Sort: for answer_rate worst first (ascending), for hold_time worst first (descending)
        if metric == "answer_rate":
            items.sort(key=lambda x: x["value"])
        else:
            items.sort(key=lambda x: x["value"], reverse=True)

        return {"metric": metric, "team_average": team_avg, "items": items}

    else:
        # Queue-level drill-down for abandoned, avg_wait, service_level
        rows = await conn.execute_fetchall(
            f"""SELECT
                COALESCE(pq.name, 'Direct') as queue_name,
                COUNT(pc.id) as offered,
                SUM(CASE WHEN pc.result = 'connected' THEN 1 ELSE 0 END) as answered,
                SUM(CASE WHEN pc.result = 'abandoned' THEN 1 ELSE 0 END) as abandoned,
                AVG(pc.wait_time) as avg_wait,
                SUM(CASE WHEN pc.result = 'connected' AND pc.wait_time <= 20 THEN 1 ELSE 0 END) as answered_20
            FROM phone_calls pc
            LEFT JOIN phone_queues pq ON pc.queue_id = pq.id
            WHERE pc.direction = 'inbound'
                AND {date_clause}
            GROUP BY COALESCE(pq.name, 'Direct')
            HAVING offered > 0
            ORDER BY offered DESC""",
            date_params,
        )

        items = []
        all_values = []
        for r in rows:
            qname, offered, answered, abandoned_cnt, avg_wait, ans_20 = (
                r[0], r[1], r[2], r[3], r[4] or 0, r[5],
            )
            if metric == "abandoned":
                val = round((abandoned_cnt / offered * 100) if offered > 0 else 0, 1)
            elif metric == "avg_wait":
                val = round(avg_wait)
            else:  # service_level
                val = round((ans_20 / offered * 100) if offered > 0 else 0, 1)
            all_values.append(val)
            items.append({
                "name": qname, "type": "queue", "value": val, "total_calls": offered,
            })

        team_avg = round(sum(all_values) / len(all_values), 1) if all_values else 0
        for item in items:
            item["gap"] = round(item["value"] - team_avg, 1)

        # Sort: for service_level worst first (ascending), for abandoned/avg_wait worst first (descending)
        if metric == "service_level":
            items.sort(key=lambda x: x["value"])
        else:
            items.sort(key=lambda x: x["value"], reverse=True)

        return {"metric": metric, "team_average": team_avg, "items": items}


@router.get("/sync/status")
async def phone_sync_status(request: Request):
    """Phone sync status information."""
    phone_engine = getattr(request.app.state, "phone_engine", None)

    if phone_engine is None:
        return {
            "is_syncing": False,
            "last_sync_time": None,
            "last_result": None,
            "provider": "not configured",
        }

    status = phone_engine.get_sync_status()
    provider_name = "unknown"
    if hasattr(phone_engine, "provider") and hasattr(phone_engine.provider, "get_provider_name"):
        provider_name = phone_engine.provider.get_provider_name()

    return {
        **status,
        "provider": provider_name,
    }
