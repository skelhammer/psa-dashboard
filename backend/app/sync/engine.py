"""Sync engine: orchestrates data sync from PSA provider to SQLite.

Full sync on first run, incremental syncs after that.
Uses SQLite transactions; commits only after a full sync cycle completes.

Multi-provider safe: each SyncEngine instance is bound to one provider.
A module-level asyncio.Lock prevents concurrent writes to the shared
SQLite connection (aiosqlite uses a single connection singleton).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiosqlite

from app.api.queries import get_closed_statuses_sql
from app.config import get_settings
from app.database import Database
from app.models import Client, ClientContract, Technician, Ticket, TicketFilter
from app.psa.base import PSAProvider
from app.sync.hooks import run_post_sync_hooks
from app.utils.business_hours import calculate_business_minutes

logger = logging.getLogger(__name__)

# Global lock: prevents two SyncEngines from writing concurrently.
# Both engines share one aiosqlite.Connection; without this lock an
# early commit() from engine A would capture engine B's partial data.
_sync_lock = asyncio.Lock()


def _get_closed_statuses() -> list[str]:
    return get_settings().server.closed_statuses


def _prefix(provider_name: str, raw_id: str | None) -> str:
    """Prefix a raw ID with the provider name (e.g. 'superops:12345')."""
    if not raw_id:
        return ""
    return f"{provider_name}:{raw_id}"


def _unprefix(prefixed_id: str) -> str:
    """Strip the provider prefix from an ID (e.g. 'superops:12345' -> '12345')."""
    if ":" in prefixed_id:
        return prefixed_id.split(":", 1)[1]
    return prefixed_id


class SyncEngine:
    def __init__(self, provider: PSAProvider, db: Database):
        self.provider = provider
        self.db = db
        self._last_sync_time: datetime | None = None
        self._is_syncing = False
        self._tech_merge_map: dict[str, str] = self._load_tech_merge_map()

    def _load_tech_merge_map(self) -> dict[str, str]:
        """Load tech_merge_map from config for this provider.

        Maps native provider tech IDs to already-prefixed target IDs.
        E.g. Zendesk "46144980471323" -> "superops:1211881534174470144"
        """
        settings = get_settings()
        pn = self.provider.get_provider_name().lower()
        if pn == "zendesk":
            return settings.psa.zendesk.tech_merge_map or {}
        return {}

    @property
    def provider_name(self) -> str:
        return self.provider.get_provider_name().lower()

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @property
    def last_sync_time(self) -> datetime | None:
        return self._last_sync_time

    async def full_sync(self) -> dict:
        """Run a full sync of all data from the PSA."""
        if self._is_syncing:
            logger.warning("Sync already in progress for %s, skipping", self.provider_name)
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        started_at = datetime.now()
        errors: list[str] = []
        tickets_synced = 0

        async with _sync_lock:
            conn = await self.db.get_connection()

            # Log sync start
            await conn.execute(
                "INSERT INTO sync_log (started_at, provider_name) VALUES (?, ?)",
                (started_at.isoformat(), self.provider.get_provider_name()),
            )
            await conn.commit()

            try:
                # Sync technicians
                try:
                    techs = await self.provider.get_technicians()
                    await self._sync_technicians(conn, techs)
                    logger.info("[%s] Synced %d technicians", self.provider_name, len(techs))
                except Exception as e:
                    msg = f"Failed to sync technicians: {e}"
                    logger.error(msg)
                    errors.append(msg)

                # Sync clients
                try:
                    clients = await self.provider.get_clients()
                    await self._sync_clients(conn, clients)
                    logger.info("[%s] Synced %d clients", self.provider_name, len(clients))
                except Exception as e:
                    msg = f"Failed to sync clients: {e}"
                    logger.error(msg)
                    errors.append(msg)

                # Sync contracts
                try:
                    contracts = await self.provider.get_all_contracts()
                    await self._sync_contracts(conn, contracts)
                    logger.info("[%s] Synced %d contracts", self.provider_name, len(contracts))
                except Exception as e:
                    msg = f"Failed to sync contracts: {e}"
                    logger.error(msg)
                    errors.append(msg)

                # Sync all tickets (paginate through all)
                try:
                    tickets_synced, synced_ids = await self._sync_all_tickets(conn)
                    logger.info("[%s] Synced %d tickets", self.provider_name, tickets_synced)

                    # Remove tickets that no longer exist in PSA (scoped to this provider)
                    if synced_ids:
                        deleted = await self._remove_missing_tickets(conn, synced_ids)
                        if deleted:
                            logger.info("[%s] Removed %d deleted/trashed tickets", self.provider_name, deleted)
                except Exception as e:
                    msg = f"Failed to sync tickets: {e}"
                    logger.error(msg)
                    errors.append(msg)

                # Commit all changes atomically
                await conn.commit()

                # Run post-sync hooks
                try:
                    await run_post_sync_hooks(conn, self.provider, self.provider_name)
                    await conn.commit()
                except Exception as e:
                    msg = f"Post-sync hooks failed: {e}"
                    logger.error(msg)
                    errors.append(msg)

                self._last_sync_time = datetime.now()

            except Exception as e:
                msg = f"Sync failed: {e}"
                logger.error(msg)
                errors.append(msg)
                await conn.rollback()
            finally:
                self._is_syncing = False

                # Update sync log
                completed_at = datetime.now()
                error_text = "; ".join(errors) if errors else None
                await conn.execute(
                    """UPDATE sync_log
                       SET completed_at = ?, tickets_synced = ?, errors = ?
                       WHERE started_at = ? AND provider_name = ?""",
                    (completed_at.isoformat(), tickets_synced, error_text,
                     started_at.isoformat(), self.provider.get_provider_name()),
                )
                await conn.commit()

        return {
            "status": "completed" if not errors else "completed_with_errors",
            "provider": self.provider_name,
            "tickets_synced": tickets_synced,
            "errors": errors,
            "duration_seconds": (datetime.now() - started_at).total_seconds(),
        }

    async def incremental_sync(self) -> dict:
        """Sync only tickets updated since last sync."""
        if self._last_sync_time is None:
            return await self.full_sync()

        if self._is_syncing:
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        started_at = datetime.now()
        errors: list[str] = []
        tickets_synced = 0

        async with _sync_lock:
            conn = await self.db.get_connection()

            await conn.execute(
                "INSERT INTO sync_log (started_at, provider_name) VALUES (?, ?)",
                (started_at.isoformat(), self.provider.get_provider_name()),
            )
            await conn.commit()

            try:
                tickets_synced, _ = await self._sync_all_tickets(conn, updated_since=self._last_sync_time)
                await conn.commit()

                # Re-fetch tickets with open billing flags to catch worklog updates
                try:
                    tickets_synced += await self._refresh_flagged_tickets(conn)
                    await conn.commit()
                except Exception as e:
                    logger.warning("Flagged ticket refresh failed (non-fatal): %s", e)

                # Prune open tickets that were deleted/trashed in PSA
                try:
                    pruned = await self._prune_deleted_open_tickets(conn)
                    if pruned:
                        await conn.commit()
                        logger.info("[%s] Pruned %d deleted/trashed open tickets", self.provider_name, pruned)
                except Exception as e:
                    logger.warning("Open ticket pruning failed (non-fatal): %s", e)

                await run_post_sync_hooks(conn, self.provider, self.provider_name)
                await conn.commit()

                self._last_sync_time = datetime.now()
                logger.info("[%s] Incremental sync: %d tickets updated", self.provider_name, tickets_synced)

            except Exception as e:
                msg = f"Incremental sync failed: {e}"
                logger.error(msg)
                errors.append(msg)
                await conn.rollback()
            finally:
                self._is_syncing = False
                completed_at = datetime.now()
                error_text = "; ".join(errors) if errors else None
                await conn.execute(
                    """UPDATE sync_log
                       SET completed_at = ?, tickets_synced = ?, errors = ?
                       WHERE started_at = ? AND provider_name = ?""",
                    (completed_at.isoformat(), tickets_synced, error_text,
                     started_at.isoformat(), self.provider.get_provider_name()),
                )
                await conn.commit()

        return {
            "status": "completed" if not errors else "completed_with_errors",
            "provider": self.provider_name,
            "tickets_synced": tickets_synced,
            "errors": errors,
        }

    async def _sync_all_tickets(self, conn: aiosqlite.Connection, updated_since: datetime | None = None) -> tuple[int, set[str]]:
        """Fetch and upsert all tickets, paginating through results.

        Returns (count, set_of_prefixed_ids).
        """
        page = 1
        total = 0
        synced_ids: set[str] = set()
        max_pages = 100

        while page <= max_pages:
            filters = TicketFilter(
                page=page,
                page_size=100,
                updated_since=updated_since,
            )
            result = await self.provider.get_tickets(filters)

            for ticket in result.items:
                await self._upsert_ticket(conn, ticket)
                synced_ids.add(_prefix(self.provider_name, ticket.id))
                total += 1

            if not result.has_more:
                break
            page += 1

        return total, synced_ids

    async def _remove_missing_tickets(self, conn: aiosqlite.Connection, synced_ids: set[str]) -> int:
        """Delete local tickets that were not returned by a full sync.

        Scoped to current provider only to avoid deleting other providers' data.
        """
        rows = await conn.execute_fetchall(
            "SELECT id FROM tickets WHERE provider = ?",
            (self.provider_name,),
        )
        local_ids = {row["id"] for row in rows}
        missing = local_ids - synced_ids

        if missing:
            placeholders = ",".join("?" for _ in missing)
            await conn.execute(
                f"DELETE FROM billing_flags WHERE ticket_id IN ({placeholders})",
                list(missing),
            )
            await conn.execute(
                f"DELETE FROM tickets WHERE id IN ({placeholders})",
                list(missing),
            )
            logger.info("[%s] Removed %d tickets no longer in PSA: %s",
                        self.provider_name, len(missing), [m for m in list(missing)[:10]])

        return len(missing)

    async def _prune_deleted_open_tickets(self, conn: aiosqlite.Connection) -> int:
        """Check locally-open tickets against PSA and remove any that no longer exist.

        Scoped to current provider only.
        """
        closed_statuses = _get_closed_statuses()
        closed_placeholders = ",".join("?" for _ in closed_statuses)
        local_open = await conn.execute_fetchall(
            f"SELECT id FROM tickets WHERE provider = ? AND status NOT IN ({closed_placeholders})",
            [self.provider_name, *closed_statuses],
        )
        if not local_open:
            return 0

        local_open_ids = {row["id"] for row in local_open}

        # Fetch all open tickets from PSA (just IDs)
        remote_open_ids: set[str] = set()
        page = 1
        while page <= 20:
            filters = TicketFilter(
                page=page,
                page_size=100,
                exclude_statuses=list(closed_statuses),
            )
            result = await self.provider.get_tickets(filters)
            for ticket in result.items:
                remote_open_ids.add(_prefix(self.provider_name, ticket.id))
            if not result.has_more:
                break
            page += 1

        # Safety check: if remote returned very few tickets compared to local,
        # something might be wrong with the API. Skip pruning.
        if len(remote_open_ids) < len(local_open_ids) * 0.5 and len(local_open_ids) > 10:
            logger.warning(
                "[%s] Skipping open ticket pruning: remote has %d open vs %d local. Possible API issue.",
                self.provider_name, len(remote_open_ids), len(local_open_ids),
            )
            return 0

        missing = local_open_ids - remote_open_ids
        if missing:
            placeholders = ",".join("?" for _ in missing)
            await conn.execute(
                f"DELETE FROM billing_flags WHERE ticket_id IN ({placeholders})",
                list(missing),
            )
            await conn.execute(
                f"DELETE FROM tickets WHERE id IN ({placeholders})",
                list(missing),
            )
            logger.info("[%s] Pruned %d open tickets no longer in PSA: %s",
                        self.provider_name, len(missing), [m for m in list(missing)[:10]])

        return len(missing)

    async def _refresh_flagged_tickets(self, conn: aiosqlite.Connection) -> int:
        """Re-fetch tickets with open billing flags to catch worklog updates.

        Scoped to current provider only.
        """
        flagged = await conn.execute_fetchall(
            """SELECT DISTINCT t.id
               FROM billing_flags bf
               JOIN tickets t ON t.id = bf.ticket_id
               WHERE bf.resolved = 0 AND t.provider = ?""",
            (self.provider_name,),
        )
        if not flagged:
            return 0

        prefixed_ids = [row[0] for row in flagged]
        logger.info("[%s] Refreshing %d tickets with open billing flags", self.provider_name, len(prefixed_ids))

        refreshed = 0
        for prefixed_id in prefixed_ids:
            native_id = _unprefix(prefixed_id)
            filters = TicketFilter(page=1, page_size=1, ticket_ids=[native_id])
            result = await self.provider.get_tickets(filters)
            for ticket in result.items:
                await self._upsert_ticket(conn, ticket)
                refreshed += 1

        if refreshed:
            logger.info("[%s] Refreshed %d flagged tickets", self.provider_name, refreshed)
        return refreshed

    def _resolve_tech_id(self, native_tech_id: str | None) -> str | None:
        """Resolve a native technician ID, applying tech_merge_map if configured.

        If the tech is in the merge map, returns the already-prefixed target ID
        (e.g. 'superops:12345'). Otherwise, prefixes with this provider's name.
        """
        if not native_tech_id:
            return None
        merged = self._tech_merge_map.get(native_tech_id)
        if merged:
            return merged  # Already prefixed (e.g. "superops:12345")
        return _prefix(self.provider_name, native_tech_id)

    def _is_tech_merged(self, native_tech_id: str | None) -> bool:
        """Check if a technician ID is in the merge map."""
        if not native_tech_id:
            return False
        return native_tech_id in self._tech_merge_map

    async def _upsert_ticket(self, conn: aiosqlite.Connection, ticket: Ticket):
        """Insert or update a ticket in the database with provider-prefixed IDs."""
        now = datetime.now().isoformat()
        pn = self.provider_name
        prefixed_id = _prefix(pn, ticket.id)

        # Check if ticket was previously resolved (for reopened detection)
        existing = await conn.execute_fetchall(
            "SELECT resolution_time, status FROM tickets WHERE id = ?",
            (prefixed_id,),
        )

        reopened = False
        if existing:
            old_res_time = existing[0][0]
            old_status = existing[0][1]
            if old_res_time and ticket.status not in _get_closed_statuses():
                reopened = True
            if not reopened:
                old_reopened = await conn.execute_fetchall(
                    "SELECT reopened FROM tickets WHERE id = ?", (prefixed_id,),
                )
                if old_reopened and old_reopened[0][0]:
                    reopened = True
        else:
            if ticket.resolution_time and ticket.status not in _get_closed_statuses():
                reopened = True

        # Resolve technician name: if merged, look up canonical name from technicians table
        resolved_tech_id = self._resolve_tech_id(ticket.technician_id)
        resolved_tech_name = ticket.technician_name
        if self._is_tech_merged(ticket.technician_id) and resolved_tech_id:
            canonical = await conn.execute_fetchall(
                "SELECT first_name, last_name FROM technicians WHERE id = ?",
                (resolved_tech_id,),
            )
            if canonical:
                fn, ln = canonical[0][0] or "", canonical[0][1] or ""
                resolved_tech_name = f"{fn} {ln}".strip() or resolved_tech_name

        await conn.execute(
            """INSERT OR REPLACE INTO tickets (
                id, display_id, subject, ticket_type, source,
                client_id, client_name, site_id, site_name,
                requester_id, requester_name,
                tech_group_id, tech_group_name,
                technician_id, technician_name,
                status, priority, impact, urgency,
                category, subcategory,
                sla_id, sla_name,
                created_time, updated_time,
                first_response_due, first_response_time, first_response_violated,
                resolution_due, resolution_time, resolution_violated,
                worklog_hours,
                conversation_count, tech_reply_count,
                last_conversation_time, last_responder_type,
                reopened, provider, is_corp, fcr, synced_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?, ?
            )""",
            (
                prefixed_id, ticket.display_id, ticket.subject, ticket.ticket_type, ticket.source,
                _prefix(pn, ticket.client_id) if ticket.client_id else "",
                ticket.client_name,
                ticket.site_id, ticket.site_name,
                _prefix(pn, ticket.requester_id) if ticket.requester_id else "",
                ticket.requester_name,
                _prefix(pn, ticket.tech_group_id) if ticket.tech_group_id else None,
                ticket.tech_group_name,
                resolved_tech_id,
                resolved_tech_name,
                ticket.status, ticket.priority, ticket.impact, ticket.urgency,
                ticket.category, ticket.subcategory,
                _prefix(pn, ticket.sla_id) if ticket.sla_id else None,
                ticket.sla_name,
                ticket.created_time.isoformat(), ticket.updated_time.isoformat(),
                ticket.first_response_due.isoformat() if ticket.first_response_due else None,
                ticket.first_response_time.isoformat() if ticket.first_response_time else None,
                1 if ticket.first_response_violated else (0 if ticket.first_response_violated is False else None),
                ticket.resolution_due.isoformat() if ticket.resolution_due else None,
                ticket.resolution_time.isoformat() if ticket.resolution_time else None,
                1 if ticket.resolution_violated else (0 if ticket.resolution_violated is False else None),
                ticket.worklog_hours,
                0, 0,  # conversation_count, tech_reply_count (updated by hooks)
                None, None,  # last_conversation_time, last_responder_type (updated by hooks)
                1 if reopened else 0,
                pn,
                1 if ticket.is_corp else 0,
                1 if ticket.fcr else 0,
                now,
            ),
        )

        # Calculate and store business-hours durations
        await self._update_business_minutes(conn, ticket, prefixed_id)

    async def _update_business_minutes(self, conn: aiosqlite.Connection, ticket: Ticket, prefixed_id: str):
        """Calculate and store business-hours duration metrics for a ticket."""
        settings = get_settings()
        bh_config = settings.business_hours

        fr_minutes = None
        res_minutes = None

        tz_name = settings.server.timezone

        if ticket.first_response_time and ticket.created_time:
            if bh_config.enabled:
                fr_minutes = calculate_business_minutes(
                    ticket.created_time, ticket.first_response_time, bh_config, tz_name,
                )
            else:
                fr_minutes = (ticket.first_response_time - ticket.created_time).total_seconds() / 60

        if ticket.resolution_time and ticket.created_time:
            if bh_config.enabled:
                res_minutes = calculate_business_minutes(
                    ticket.created_time, ticket.resolution_time, bh_config, tz_name,
                )
            else:
                res_minutes = (ticket.resolution_time - ticket.created_time).total_seconds() / 60

        await conn.execute(
            """UPDATE tickets
               SET first_response_business_minutes = ?,
                   resolution_business_minutes = ?
               WHERE id = ?""",
            (fr_minutes, res_minutes, prefixed_id),
        )

    async def _sync_technicians(self, conn: aiosqlite.Connection, techs: list[Technician]):
        pn = self.provider_name
        for tech in techs:
            # Skip techs that are merged into another provider's record
            if tech.id in self._tech_merge_map:
                continue
            prefixed_id = _prefix(pn, tech.id)
            await conn.execute(
                """INSERT INTO technicians (id, first_name, last_name, email, role, provider)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       first_name = excluded.first_name,
                       last_name = excluded.last_name,
                       email = excluded.email,
                       role = excluded.role,
                       provider = excluded.provider""",
                (prefixed_id, tech.first_name, tech.last_name, tech.email, tech.role, pn),
            )

    async def _sync_clients(self, conn: aiosqlite.Connection, clients: list[Client]):
        pn = self.provider_name
        for client in clients:
            prefixed_id = _prefix(pn, client.id)
            await conn.execute(
                """INSERT OR REPLACE INTO clients
                   (id, name, plan, stage, status, profit_type, account_number, provider)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (prefixed_id, client.name, client.plan, client.stage,
                 client.status, client.profit_type, client.account_number, pn),
            )

    async def _sync_contracts(self, conn: aiosqlite.Connection, contracts: list[ClientContract]):
        pn = self.provider_name
        now = datetime.now().isoformat()
        for contract in contracts:
            await conn.execute(
                """INSERT OR REPLACE INTO client_contracts
                   (contract_id, client_id, client_name, contract_type, contract_name,
                    status, start_date, end_date, provider, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _prefix(pn, contract.contract_id),
                    _prefix(pn, contract.client_id),
                    contract.client_name,
                    contract.contract_type, contract.contract_name,
                    contract.status,
                    str(contract.start_date) if contract.start_date else None,
                    str(contract.end_date) if contract.end_date else None,
                    pn,
                    now,
                ),
            )
