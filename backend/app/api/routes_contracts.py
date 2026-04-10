"""Contracts API: list expiring contracts and manage manual overrides.

Scoped to SuperOps provider only per product requirements. Manual entries and
overrides use source='manual' so the sync engine leaves them alone.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["contracts"])

PROVIDER = "superops"
VALID_TERMS = {1, 2, 3}

# The four MSP service plans we sell. These string values match exactly the
# contract_name values that come from SuperOps and the client.plan custom field.
MSP_PLANS = ["MSP Basic", "MSP Advanced", "MSP Premium", "MSP Platinum"]
MSP_PLAN_KEYS = {
    "msp_basic": "MSP Basic",
    "msp_advanced": "MSP Advanced",
    "msp_premium": "MSP Premium",
    "msp_platinum": "MSP Platinum",
}


class ContractIn(BaseModel):
    """Payload for creating a manual contract."""
    client_id: str
    contract_name: str | None = None
    contract_type: str = "managed"
    start_date: str | None = None  # ISO date (YYYY-MM-DD)
    end_date: str | None = None
    term_length_years: int | None = Field(default=None, ge=1, le=3)
    notes: str | None = None


class ContractUpdate(BaseModel):
    """Payload for updating a contract. Any provided field overrides the synced value."""
    contract_name: str | None = None
    contract_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    term_length_years: int | None = Field(default=None, ge=1, le=3)
    notes: str | None = None
    status: str | None = None


def _parse_iso_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except (ValueError, TypeError):
        return None


def _days_until(end: date | None, today: date) -> int | None:
    if end is None:
        return None
    return (end - today).days


def _expiry_bucket(days: int | None) -> str:
    if days is None:
        return "no_expiry"
    if days < 0:
        return "expired"
    if days <= 30:
        return "expiring_30"
    if days <= 60:
        return "expiring_60"
    if days <= 90:
        return "expiring_90"
    return "safe"


def _derive_term_years(start: date | None, end: date | None) -> int | None:
    """Best effort term length from dates, rounded to nearest year in {1, 2, 3}."""
    if not start or not end:
        return None
    days = (end - start).days
    if days <= 0:
        return None
    years = round(days / 365)
    if years in VALID_TERMS:
        return years
    return None


def _plan_clause(plan: str) -> tuple[str, list]:
    """Build a SQL fragment + params that scopes contracts to a plan selection.

    plan values:
      - msp_all (default): contract_name in any of the 4 MSP plans
      - msp_basic / msp_advanced / msp_premium / msp_platinum: single plan
      - all: no scoping (returns Microsoft, Azure, etc. as well)
    """
    if plan == "all":
        return "", []
    if plan in MSP_PLAN_KEYS:
        return "contract_name = ?", [MSP_PLAN_KEYS[plan]]
    # default and any unknown value falls back to msp_all
    placeholders = ",".join("?" for _ in MSP_PLANS)
    return f"contract_name IN ({placeholders})", list(MSP_PLANS)


@router.get("/contracts")
async def list_contracts(
    request: Request,
    filter: str = Query("active", description="active | expiring_30 | expiring_60 | expiring_90 | expired | all"),
    plan: str = Query("msp_all", description="msp_all | msp_basic | msp_advanced | msp_premium | msp_platinum | all"),
    search: str | None = Query(None, description="Client name substring search"),
):
    """List SuperOps contracts, sorted by end_date ascending.

    Status filters:
      - active: currently in effect (no end_date, or end_date >= today) and status != terminated
      - expiring_30/60/90: active contracts expiring within N days
      - expired: end_date in the past
      - all: everything tied to SuperOps

    Plan filter scopes contracts by their contract_name. Default 'msp_all' hides
    add-on contracts (Microsoft 365, Azure, etc.) and only shows the 4 MSP plans
    that drive renewal conversations.
    """
    db = request.app.state.db
    conn = await db.get_connection()

    today = date.today()
    today_iso = today.isoformat()

    plan_sql, plan_params = _plan_clause(plan)

    conditions = ["provider = ?"]
    params: list = [PROVIDER]
    if plan_sql:
        conditions.append(plan_sql)
        params.extend(plan_params)

    if filter == "active":
        conditions.append("(end_date IS NULL OR end_date >= ?)")
        params.append(today_iso)
        conditions.append("LOWER(status) != 'terminated'")
    elif filter == "expiring_30":
        conditions.append("end_date IS NOT NULL AND end_date >= ? AND end_date <= date(?, '+30 days')")
        params.extend([today_iso, today_iso])
    elif filter == "expiring_60":
        conditions.append("end_date IS NOT NULL AND end_date >= ? AND end_date <= date(?, '+60 days')")
        params.extend([today_iso, today_iso])
    elif filter == "expiring_90":
        conditions.append("end_date IS NOT NULL AND end_date >= ? AND end_date <= date(?, '+90 days')")
        params.extend([today_iso, today_iso])
    elif filter == "expired":
        conditions.append("end_date IS NOT NULL AND end_date < ?")
        params.append(today_iso)
    # "all" adds no extra condition

    if search:
        conditions.append("LOWER(client_name) LIKE ?")
        params.append(f"%{search.lower()}%")

    where = " AND ".join(conditions)

    rows = await conn.execute_fetchall(
        f"""SELECT contract_id, client_id, client_name, contract_type, contract_name,
                   status, start_date, end_date, term_length_years, source, notes,
                   synced_at
           FROM client_contracts
           WHERE {where}
           ORDER BY
               CASE WHEN end_date IS NULL THEN 1 ELSE 0 END,
               end_date ASC,
               client_name ASC""",
        params,
    )

    contracts = []
    for row in rows:
        start = _parse_iso_date(row["start_date"])
        end = _parse_iso_date(row["end_date"])
        days = _days_until(end, today)
        term = row["term_length_years"]
        if term is None:
            term = _derive_term_years(start, end)

        contracts.append({
            "contract_id": row["contract_id"],
            "client_id": row["client_id"],
            "client_name": row["client_name"],
            "contract_type": row["contract_type"],
            "contract_name": row["contract_name"],
            "status": row["status"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "term_length_years": term,
            "source": row["source"] or "synced",
            "notes": row["notes"],
            "days_until_expiry": days,
            "expiry_bucket": _expiry_bucket(days),
            "synced_at": row["synced_at"],
        })

    # Summary counts within the current plan scope (ignoring status filter) so
    # the chip counts reflect what the user is actually looking at.
    summary_where = "provider = ?"
    summary_params: list = [PROVIDER]
    if plan_sql:
        summary_where += f" AND {plan_sql}"
        summary_params.extend(plan_params)
    summary_rows = await conn.execute_fetchall(
        f"SELECT end_date, status FROM client_contracts WHERE {summary_where}",
        summary_params,
    )
    counts = {
        "active": 0,
        "expiring_30": 0,
        "expiring_60": 0,
        "expiring_90": 0,
        "expired": 0,
        "all": len(summary_rows),
    }
    for r in summary_rows:
        end = _parse_iso_date(r["end_date"])
        status = (r["status"] or "").lower()
        days = _days_until(end, today)
        if end is None or (days is not None and days >= 0):
            if status != "terminated":
                counts["active"] += 1
        if days is not None:
            if days < 0:
                counts["expired"] += 1
            else:
                if days <= 30:
                    counts["expiring_30"] += 1
                if days <= 60:
                    counts["expiring_60"] += 1
                if days <= 90:
                    counts["expiring_90"] += 1

    return {
        "contracts": contracts,
        "count": len(contracts),
        "summary": counts,
        "filter": filter,
        "plan": plan,
        "today": today_iso,
    }


@router.post("/contracts")
async def create_contract(body: ContractIn, request: Request):
    """Create a manual contract entry. Client must be a SuperOps client."""
    db = request.app.state.db
    conn = await db.get_connection()

    # Validate client exists and is on the SuperOps provider
    client_rows = await conn.execute_fetchall(
        "SELECT id, name, provider FROM clients WHERE id = ?", (body.client_id,),
    )
    if not client_rows:
        raise HTTPException(status_code=404, detail=f"Client {body.client_id} not found")
    client = client_rows[0]
    if client["provider"] != PROVIDER:
        raise HTTPException(
            status_code=400,
            detail=f"Manual contracts are only allowed for {PROVIDER} clients",
        )

    if body.term_length_years is not None and body.term_length_years not in VALID_TERMS:
        raise HTTPException(status_code=400, detail="term_length_years must be 1, 2, or 3")

    contract_id = f"{PROVIDER}:manual-{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    await conn.execute(
        """INSERT INTO client_contracts
           (contract_id, client_id, client_name, contract_type, contract_name,
            status, start_date, end_date, provider, synced_at,
            term_length_years, source, notes)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, 'manual', ?)""",
        (
            contract_id,
            body.client_id,
            client["name"],
            body.contract_type or "managed",
            body.contract_name,
            body.start_date,
            body.end_date,
            PROVIDER,
            now,
            body.term_length_years,
            body.notes,
        ),
    )
    await conn.commit()
    return {"status": "created", "contract_id": contract_id}


@router.patch("/contracts/{contract_id}")
async def update_contract(contract_id: str, body: ContractUpdate, request: Request):
    """Update a contract. Any edit flips source to 'manual' so sync will not overwrite it."""
    db = request.app.state.db
    conn = await db.get_connection()

    existing = await conn.execute_fetchall(
        "SELECT contract_id, provider FROM client_contracts WHERE contract_id = ?",
        (contract_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")
    if existing[0]["provider"] != PROVIDER:
        raise HTTPException(status_code=400, detail="Only SuperOps contracts are editable here")

    if body.term_length_years is not None and body.term_length_years not in VALID_TERMS:
        raise HTTPException(status_code=400, detail="term_length_years must be 1, 2, or 3")

    # Build dynamic SET clause for provided fields only
    sets: list[str] = []
    params: list = []
    for field_name in ("contract_name", "contract_type", "start_date", "end_date",
                       "term_length_years", "notes", "status"):
        value = getattr(body, field_name)
        if value is not None:
            sets.append(f"{field_name} = ?")
            params.append(value)

    if not sets:
        return {"status": "unchanged", "contract_id": contract_id}

    sets.append("source = 'manual'")
    params.append(contract_id)

    await conn.execute(
        f"UPDATE client_contracts SET {', '.join(sets)} WHERE contract_id = ?",
        params,
    )
    await conn.commit()
    return {"status": "updated", "contract_id": contract_id}


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, request: Request):
    """Delete a contract. Synced rows will reappear on next sync; manual rows are gone for good."""
    db = request.app.state.db
    conn = await db.get_connection()

    existing = await conn.execute_fetchall(
        "SELECT source FROM client_contracts WHERE contract_id = ?", (contract_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    await conn.execute("DELETE FROM client_contracts WHERE contract_id = ?", (contract_id,))
    await conn.commit()
    return {"status": "deleted", "contract_id": contract_id, "source": existing[0]["source"]}


@router.get("/contracts/clients")
async def list_superops_clients_for_picker(request: Request):
    """Lightweight client list for the 'Add Contract' dialog picker."""
    db = request.app.state.db
    conn = await db.get_connection()

    rows = await conn.execute_fetchall(
        """SELECT id, name FROM clients
           WHERE provider = ? AND stage = 'Active'
           ORDER BY name""",
        (PROVIDER,),
    )
    return {"clients": [{"id": r["id"], "name": r["name"]} for r in rows]}
