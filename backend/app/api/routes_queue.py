"""Work Queue API: scored/ranked ticket list with KPI stats."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import median

from fastapi import APIRouter, Query, Request

from app.api.queries import CLOSED_STATUSES_SQL, get_ticket_url, ticket_row_to_dict

router = APIRouter(prefix="/api", tags=["work-queue"])


async def _get_config_weights(conn) -> dict:
    """Load work queue weights from dashboard_config."""
    rows = await conn.execute_fetchall(
        "SELECT key, value FROM dashboard_config WHERE key LIKE 'work_queue_%'"
    )
    defaults = {
        "work_queue_sla_violated_weight": 1000,
        "work_queue_priority_critical_weight": 100,
        "work_queue_priority_high_weight": 75,
        "work_queue_priority_medium_weight": 50,
        "work_queue_priority_low_weight": 25,
        "work_queue_age_weight_per_hour": 1,
        "work_queue_age_cap_hours": 168,
        "work_queue_customer_waiting_weight": 150,
        "work_queue_no_first_response_weight": 200,
        "work_queue_reopened_weight": 100,
    }
    for row in rows:
        try:
            defaults[row["key"]] = int(row["value"])
        except (ValueError, TypeError):
            pass
    return defaults


def _compute_score(ticket: dict, weights: dict, now: datetime) -> float:
    """Compute ranking score for a ticket using continuous SLA decay."""
    score = 0.0

    # SLA urgency score (continuous, no cliff effects)
    fr_violated = ticket.get("first_response_violated")
    res_violated = ticket.get("resolution_violated")

    if fr_violated or res_violated:
        # Violated: base 1000 + 2 points per minute overdue
        overdue_minutes = 0.0
        for due_str, violated in [
            (ticket.get("first_response_due"), fr_violated),
            (ticket.get("resolution_due"), res_violated),
        ]:
            if violated and due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str)
                    mins_over = (now - due_dt).total_seconds() / 60
                    overdue_minutes = max(overdue_minutes, mins_over)
                except (ValueError, TypeError):
                    pass
        score += weights["work_queue_sla_violated_weight"] + max(0, overdue_minutes) * 2
    else:
        # Not violated: continuous decay from 500 to 0 over 120 minutes
        fr_due = ticket.get("first_response_due")
        res_due = ticket.get("resolution_due")
        # Skip first response due if already responded
        fr_time = ticket.get("first_response_time")

        min_remaining = None
        for due_str, skip in [(fr_due, bool(fr_time)), (res_due, False)]:
            if due_str and not skip:
                try:
                    due_dt = datetime.fromisoformat(due_str)
                    remaining = (due_dt - now).total_seconds() / 60
                    if min_remaining is None or remaining < min_remaining:
                        min_remaining = remaining
                except (ValueError, TypeError):
                    pass

        if min_remaining is not None:
            if min_remaining <= 0:
                # Past due but not flagged as violated yet
                score += weights["work_queue_sla_violated_weight"]
            elif min_remaining <= 120:
                # Continuous: 500 at 0 min remaining, 0 at 120 min remaining
                score += max(0, 500 * (1 - min_remaining / 120))
            # >120 min: 0 points (safe)

    # Priority score
    priority = ticket.get("priority", "Medium")
    priority_map = {
        "Critical": weights["work_queue_priority_critical_weight"],
        "Urgent": weights["work_queue_priority_critical_weight"],
        "High": weights["work_queue_priority_high_weight"],
        "Medium": weights["work_queue_priority_medium_weight"],
        "Low": weights["work_queue_priority_low_weight"],
        "Very Low": weights["work_queue_priority_low_weight"],
    }
    score += priority_map.get(priority, weights["work_queue_priority_medium_weight"])

    # Age bonus (capped to prevent ancient tickets dominating)
    created = ticket.get("created_time")
    age_cap = weights["work_queue_age_cap_hours"]
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            age_hours = (now - created_dt).total_seconds() / 3600
            score += min(age_hours, age_cap) * weights["work_queue_age_weight_per_hour"]
        except (ValueError, TypeError):
            pass

    # Customer waiting boost (customer replied, tech hasn't)
    if ticket.get("last_responder_type") == "requester":
        score += weights["work_queue_customer_waiting_weight"]

    # No first response boost (customer has received zero acknowledgement)
    if not ticket.get("first_response_time") and created:
        try:
            created_dt = datetime.fromisoformat(created)
            age_min = (now - created_dt).total_seconds() / 60
            if age_min > 15:  # Skip brand-new tickets (<15 min old)
                score += weights["work_queue_no_first_response_weight"]
        except (ValueError, TypeError):
            pass

    # Reopened boost (failed resolution deserves attention)
    if ticket.get("reopened"):
        score += weights["work_queue_reopened_weight"]

    return score


def _build_queue_query(
    client_id: str | None,
    technician_id: str | None,
    priority: str | None,
    status: str | None,
    tech_group: str | None,
    provider: str | None,
    hide_corp: bool,
    unassigned_only: bool,
) -> tuple[str, list]:
    """Build the WHERE clause for work queue queries."""
    conditions = [f"status NOT IN {CLOSED_STATUSES_SQL}"]
    params: list = []

    if client_id:
        conditions.append("client_id = ?")
        params.append(client_id)
    if technician_id:
        conditions.append("technician_id = ?")
        params.append(technician_id)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if tech_group:
        conditions.append("COALESCE(tech_group_name, 'Tier 1 Support') = ?")
        params.append(tech_group)
    if provider:
        conditions.append("provider = ?")
        params.append(provider)
    if hide_corp:
        conditions.append("is_corp = 0")
    if unassigned_only:
        conditions.append("(technician_id IS NULL OR technician_id = '')")

    where = " AND ".join(conditions)
    return where, params



@router.get("/work-queue")
async def work_queue(
    request: Request,
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    tech_group: str | None = Query(None),
    provider: str | None = Query(None),
    hide_corp: bool = Query(False),
    unassigned_only: bool = Query(False),
):
    """Get prioritized work queue of open tickets."""
    db = request.app.state.db
    conn = await db.get_connection()

    where, params = _build_queue_query(
        client_id, technician_id, priority, status,
        tech_group, provider, hide_corp, unassigned_only,
    )

    rows = await conn.execute_fetchall(
        f"SELECT * FROM tickets WHERE {where}",
        params,
    )

    tickets = [ticket_row_to_dict(row) for row in rows]

    weights = await _get_config_weights(conn)
    now = datetime.now()

    for ticket in tickets:
        ticket["score"] = _compute_score(ticket, weights, now)
        ticket["url"] = get_ticket_url(ticket["id"], request.app.state.providers)

    tickets.sort(key=lambda t: t["score"], reverse=True)
    for i, ticket in enumerate(tickets, 1):
        ticket["rank"] = i

    return {"tickets": tickets, "count": len(tickets)}


@router.get("/work-queue/stats")
async def work_queue_stats(
    request: Request,
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    tech_group: str | None = Query(None),
    provider: str | None = Query(None),
    hide_corp: bool = Query(False),
    unassigned_only: bool = Query(False),
):
    """Get aggregated KPI stats and chart data for the work queue."""
    db = request.app.state.db
    conn = await db.get_connection()

    where, params = _build_queue_query(
        client_id, technician_id, priority, status,
        tech_group, provider, hide_corp, unassigned_only,
    )

    rows = await conn.execute_fetchall(
        f"SELECT * FROM tickets WHERE {where}",
        params,
    )

    tickets = [ticket_row_to_dict(row) for row in rows]
    weights = await _get_config_weights(conn)
    now = datetime.now()

    # Compute scores
    scores = []
    for ticket in tickets:
        ticket["score"] = _compute_score(ticket, weights, now)
        scores.append(ticket["score"])

    queue_depth = len(tickets)

    # KPI calculations
    unassigned_count = sum(
        1 for t in tickets if not t.get("technician_id") or t["technician_id"] == ""
    )

    sla_violated_count = 0
    sla_breaching_count = 0
    for t in tickets:
        if t.get("first_response_violated") or t.get("resolution_violated"):
            sla_violated_count += 1
        else:
            # Check if breaching within 120 min
            for due_str, skip in [
                (t.get("first_response_due"), bool(t.get("first_response_time"))),
                (t.get("resolution_due"), False),
            ]:
                if due_str and not skip:
                    try:
                        due_dt = datetime.fromisoformat(due_str)
                        remaining = (due_dt - now).total_seconds() / 60
                        if remaining <= 0:
                            sla_violated_count += 1
                        elif remaining <= 120:
                            sla_breaching_count += 1
                        break
                    except (ValueError, TypeError):
                        pass

    high_critical_count = sum(
        1 for t in tickets if t.get("priority") in ("Critical", "Urgent", "High")
    )

    awaiting_tech_count = sum(
        1 for t in tickets if t.get("last_responder_type") == "requester"
    )

    no_first_response_count = sum(
        1 for t in tickets if not t.get("first_response_time")
    )

    # Age calculations
    ages_minutes = []
    for t in tickets:
        ct = t.get("created_time")
        if ct:
            try:
                created_dt = datetime.fromisoformat(ct)
                ages_minutes.append((now - created_dt).total_seconds() / 60)
            except (ValueError, TypeError):
                pass

    avg_age_minutes = sum(ages_minutes) / len(ages_minutes) if ages_minutes else 0
    oldest_age_minutes = max(ages_minutes) if ages_minutes else 0

    # First response times from raw row data (not in ticket_row_to_dict)
    fr_minutes = []
    for row in rows:
        if "first_response_business_minutes" in row.keys():
            val = row["first_response_business_minutes"]
            if val is not None:
                try:
                    fr_minutes.append(float(val))
                except (ValueError, TypeError):
                    pass

    avg_first_response_minutes = (
        round(sum(fr_minutes) / len(fr_minutes), 1) if fr_minutes else None
    )

    # Score stats
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    median_score = round(median(scores), 1) if scores else 0

    # Chart data: by priority
    priority_counter: Counter = Counter()
    for t in tickets:
        priority_counter[t.get("priority", "Unknown")] += 1
    priority_order = ["Critical", "Urgent", "High", "Medium", "Low", "Very Low"]
    by_priority = [
        {"priority": p, "count": priority_counter[p]}
        for p in priority_order
        if priority_counter[p] > 0
    ]

    # Chart data: by technician (top 15)
    tech_counter: Counter = Counter()
    for t in tickets:
        name = t.get("technician_name") or "Unassigned"
        tech_counter[name] += 1
    by_technician = [
        {"name": name, "count": count}
        for name, count in tech_counter.most_common(15)
    ]

    # Chart data: by client (top 15)
    client_counter: Counter = Counter()
    for t in tickets:
        name = t.get("client_name") or "Unknown"
        client_counter[name] += 1
    by_client = [
        {"name": name, "count": count}
        for name, count in client_counter.most_common(15)
    ]

    # Chart data: by status
    status_counter: Counter = Counter()
    for t in tickets:
        status_counter[t.get("status", "Unknown")] += 1
    by_status = [
        {"status": s, "count": c}
        for s, c in status_counter.most_common()
    ]

    # Chart data: score distribution buckets
    buckets = [
        ("0-100", "Low", 0, 100),
        ("100-300", "Medium", 100, 300),
        ("300-500", "High", 300, 500),
        ("500-1000", "Critical", 500, 1000),
        ("1000+", "Violated", 1000, float("inf")),
    ]
    score_dist = []
    for label, desc, lo, hi in buckets:
        count = sum(1 for s in scores if lo <= s < hi)
        score_dist.append({"bucket": label, "label": desc, "count": count})

    return {
        "kpis": {
            "queue_depth": queue_depth,
            "unassigned_count": unassigned_count,
            "unassigned_pct": round(unassigned_count / queue_depth * 100, 1) if queue_depth else 0,
            "sla_violated_count": sla_violated_count,
            "sla_breaching_count": sla_breaching_count,
            "high_critical_count": high_critical_count,
            "high_critical_pct": round(high_critical_count / queue_depth * 100, 1) if queue_depth else 0,
            "avg_age_minutes": round(avg_age_minutes, 1),
            "oldest_age_minutes": round(oldest_age_minutes, 1),
            "avg_score": avg_score,
            "median_score": median_score,
            "awaiting_tech_count": awaiting_tech_count,
            "no_first_response_count": no_first_response_count,
            "avg_first_response_minutes": avg_first_response_minutes,
        },
        "charts": {
            "by_priority": by_priority,
            "by_technician": by_technician,
            "by_client": by_client,
            "by_status": by_status,
            "score_distribution": score_dist,
        },
    }
