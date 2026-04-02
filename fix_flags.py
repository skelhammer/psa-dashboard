import sqlite3
conn = sqlite3.connect("data/metrics.db")
cur = conn.execute(
    "UPDATE billing_flags"
    " SET resolved = 1, resolved_at = datetime('now'),"
    " resolution_note = 'Bulk resolved: pre-migration tickets'"
    " WHERE resolved = 0"
    " AND ticket_id IN (SELECT id FROM tickets WHERE created_time < '2026-02-01')"
)
print(f"Resolved {cur.rowcount} flags")
conn.commit()
conn.close()
