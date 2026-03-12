"""Filter options API: lists of clients, techs, categories, statuses for dropdowns."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["filters"])


@router.get("/filters")
async def get_filter_options(request: Request):
    db = request.app.state.db
    conn = await db.get_connection()

    clients = await conn.execute_fetchall(
        "SELECT id, name FROM clients ORDER BY name"
    )
    technicians = await conn.execute_fetchall(
        "SELECT id, first_name, last_name FROM technicians ORDER BY first_name"
    )
    categories = await conn.execute_fetchall(
        "SELECT DISTINCT category FROM tickets WHERE category IS NOT NULL ORDER BY category"
    )
    statuses = await conn.execute_fetchall(
        "SELECT DISTINCT status FROM tickets ORDER BY status"
    )
    priorities = await conn.execute_fetchall(
        "SELECT DISTINCT priority FROM tickets ORDER BY priority"
    )

    return {
        "clients": [{"id": r["id"], "name": r["name"]} for r in clients],
        "technicians": [
            {"id": r["id"], "name": f"{r['first_name']} {r['last_name']}".strip()}
            for r in technicians
        ],
        "categories": [r["category"] for r in categories],
        "statuses": [r["status"] for r in statuses],
        "priorities": [r["priority"] for r in priorities],
    }
