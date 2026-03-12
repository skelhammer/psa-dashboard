"""Sync engine: orchestrates data sync from PSA provider to SQLite.

Full sync on first run, incremental syncs after that.
Uses SQLite transactions; commits only after a full sync cycle completes.
"""

from __future__ import annotations

import logging
from datetime import datetime

import aiosqlite

from app.database import Database
from app.models import Client, ClientContract, Technician, Ticket, TicketFilter
from app.psa.base import PSAProvider
from app.sync.hooks import run_post_sync_hooks

logger = logging.getLogger(__name__)

CLOSED_STATUSES = ["Resolved", "Closed"]


class SyncEngine:
    def __init__(self, provider: PSAProvider, db: Database):
        self.provider = provider
        self.db = db
        self._last_sync_time: datetime | None = None
        self._is_syncing = False

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @property
    def last_sync_time(self) -> datetime | None:
        return self._last_sync_time

    async def full_sync(self) -> dict:
        """Run a full sync of all data from the PSA."""
        if self._is_syncing:
            logger.warning("Sync already in progress, skipping")
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        started_at = datetime.now()
        conn = await self.db.get_connection()
        errors: list[str] = []
        tickets_synced = 0

        # Log sync start
        await conn.execute(
            "INSERT INTO sync_log (started_at, provider_name) VALUES (?, ?)",
            (started_at.isoformat(), self.provider.get_provider_name()),
        )
        sync_id = (await conn.execute("SELECT last_insert_rowid()")).fetchone
        await conn.commit()

        try:
            # Sync technicians
            try:
                techs = await self.provider.get_technicians()
                await self._sync_technicians(conn, techs)
                logger.info("Synced %d technicians", len(techs))
            except Exception as e:
                msg = f"Failed to sync technicians: {e}"
                logger.error(msg)
                errors.append(msg)

            # Sync clients
            try:
                clients = await self.provider.get_clients()
                await self._sync_clients(conn, clients)
                logger.info("Synced %d clients", len(clients))
            except Exception as e:
                msg = f"Failed to sync clients: {e}"
                logger.error(msg)
                errors.append(msg)

            # Sync contracts
            try:
                contracts = await self.provider.get_all_contracts()
                await self._sync_contracts(conn, contracts)
                logger.info("Synced %d contracts", len(contracts))
            except Exception as e:
                msg = f"Failed to sync contracts: {e}"
                logger.error(msg)
                errors.append(msg)

            # Sync all tickets (paginate through all)
            try:
                tickets_synced, synced_ids = await self._sync_all_tickets(conn)
                logger.info("Synced %d tickets", tickets_synced)

                # Remove tickets that no longer exist in PSA (trashed/deleted)
                if synced_ids:
                    deleted = await self._remove_missing_tickets(conn, synced_ids)
                    if deleted:
                        logger.info("Removed %d deleted/trashed tickets", deleted)
            except Exception as e:
                msg = f"Failed to sync tickets: {e}"
                logger.error(msg)
                errors.append(msg)

            # Commit all changes atomically
            await conn.commit()

            # Run post-sync hooks
            try:
                await run_post_sync_hooks(conn, self.provider)
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
        conn = await self.db.get_connection()
        errors: list[str] = []
        tickets_synced = 0

        await conn.execute(
            "INSERT INTO sync_log (started_at, provider_name) VALUES (?, ?)",
            (started_at.isoformat(), self.provider.get_provider_name()),
        )
        await conn.commit()

        try:
            tickets_synced, _ = await self._sync_all_tickets(conn, updated_since=self._last_sync_time)
            await conn.commit()

            # Prune open tickets that were deleted/trashed in PSA
            try:
                pruned = await self._prune_deleted_open_tickets(conn)
                if pruned:
                    await conn.commit()
                    logger.info("Pruned %d deleted/trashed open tickets", pruned)
            except Exception as e:
                logger.warning("Open ticket pruning failed (non-fatal): %s", e)

            await run_post_sync_hooks(conn, self.provider)
            await conn.commit()

            self._last_sync_time = datetime.now()
            logger.info("Incremental sync: %d tickets updated", tickets_synced)

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
            "tickets_synced": tickets_synced,
            "errors": errors,
        }

    async def _sync_all_tickets(self, conn: aiosqlite.Connection, updated_since: datetime | None = None) -> tuple[int, set[str]]:
        """Fetch and upsert all tickets, paginating through results.

        Returns (count, set_of_synced_ids).
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
                synced_ids.add(ticket.id)
                total += 1

            if not result.has_more:
                break
            page += 1

        return total, synced_ids

    async def _remove_missing_tickets(self, conn: aiosqlite.Connection, synced_ids: set[str]) -> int:
        """Delete local tickets that were not returned by a full sync (trashed/deleted in PSA)."""
        rows = await conn.execute_fetchall("SELECT id FROM tickets")
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
            logger.info("Removed %d tickets no longer in PSA: %s", len(missing),
                        [m for m in list(missing)[:10]])

        return len(missing)

    async def _prune_deleted_open_tickets(self, conn: aiosqlite.Connection) -> int:
        """Check locally-open tickets against PSA and remove any that no longer exist.

        Only checks open tickets (small set), so this is fast.
        Returns the number of tickets pruned.
        """
        open_statuses = ('Open', 'Customer Replied', 'Under Investigation', 'On Hold',
                         'Waiting on Customer', 'Waiting on third party', 'Waiting on Order', 'Scheduled')
        placeholders = ",".join("?" for _ in open_statuses)
        local_open = await conn.execute_fetchall(
            f"SELECT id FROM tickets WHERE status IN ({placeholders})",
            list(open_statuses),
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
                exclude_statuses=list(CLOSED_STATUSES),
            )
            result = await self.provider.get_tickets(filters)
            for ticket in result.items:
                remote_open_ids.add(ticket.id)
            if not result.has_more:
                break
            page += 1

        # Safety check: if remote returned very few tickets compared to local,
        # something might be wrong with the API. Skip pruning.
        if len(remote_open_ids) < len(local_open_ids) * 0.5 and len(local_open_ids) > 10:
            logger.warning(
                "Skipping open ticket pruning: remote has %d open vs %d local. Possible API issue.",
                len(remote_open_ids), len(local_open_ids),
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
            logger.info("Pruned %d open tickets no longer in PSA: %s",
                        len(missing), [m for m in list(missing)[:10]])

        return len(missing)

    async def _upsert_ticket(self, conn: aiosqlite.Connection, ticket: Ticket):
        """Insert or update a ticket in the database."""
        now = datetime.now().isoformat()

        # Check if ticket was previously resolved (for reopened detection)
        existing = await conn.execute_fetchall(
            "SELECT resolution_time, status FROM tickets WHERE id = ?",
            (ticket.id,),
        )

        reopened = False
        if existing:
            old_res_time = existing[0][0]
            old_status = existing[0][1]
            # If it had a resolution_time and now status is not closed, it was reopened
            if old_res_time and ticket.status not in CLOSED_STATUSES:
                reopened = True
            # Preserve existing reopened flag
            if not reopened:
                old_reopened = await conn.execute_fetchall(
                    "SELECT reopened FROM tickets WHERE id = ?", (ticket.id,),
                )
                if old_reopened and old_reopened[0][0]:
                    reopened = True

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
                worklog_minutes,
                conversation_count, tech_reply_count,
                last_conversation_time, last_responder_type,
                reopened, synced_at
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
                ?, ?
            )""",
            (
                ticket.id, ticket.display_id, ticket.subject, ticket.ticket_type, ticket.source,
                ticket.client_id, ticket.client_name, ticket.site_id, ticket.site_name,
                ticket.requester_id, ticket.requester_name,
                ticket.tech_group_id, ticket.tech_group_name,
                ticket.technician_id, ticket.technician_name,
                ticket.status, ticket.priority, ticket.impact, ticket.urgency,
                ticket.category, ticket.subcategory,
                ticket.sla_id, ticket.sla_name,
                ticket.created_time.isoformat(), ticket.updated_time.isoformat(),
                ticket.first_response_due.isoformat() if ticket.first_response_due else None,
                ticket.first_response_time.isoformat() if ticket.first_response_time else None,
                1 if ticket.first_response_violated else (0 if ticket.first_response_violated is False else None),
                ticket.resolution_due.isoformat() if ticket.resolution_due else None,
                ticket.resolution_time.isoformat() if ticket.resolution_time else None,
                1 if ticket.resolution_violated else (0 if ticket.resolution_violated is False else None),
                ticket.worklog_minutes,
                0, 0,  # conversation_count, tech_reply_count (updated by hooks)
                None, None,  # last_conversation_time, last_responder_type (updated by hooks)
                1 if reopened else 0,
                now,
            ),
        )

    async def _sync_technicians(self, conn: aiosqlite.Connection, techs: list[Technician]):
        for tech in techs:
            await conn.execute(
                """INSERT OR REPLACE INTO technicians (id, first_name, last_name, email, role)
                   VALUES (?, ?, ?, ?, ?)""",
                (tech.id, tech.first_name, tech.last_name, tech.email, tech.role),
            )

    async def _sync_clients(self, conn: aiosqlite.Connection, clients: list[Client]):
        for client in clients:
            await conn.execute(
                """INSERT OR REPLACE INTO clients
                   (id, name, plan, stage, status, profit_type, account_number)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (client.id, client.name, client.plan, client.stage,
                 client.status, client.profit_type, client.account_number),
            )

    async def _sync_contracts(self, conn: aiosqlite.Connection, contracts: list[ClientContract]):
        now = datetime.now().isoformat()
        for contract in contracts:
            await conn.execute(
                """INSERT OR REPLACE INTO client_contracts
                   (contract_id, client_id, client_name, contract_type, contract_name,
                    status, start_date, end_date, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    contract.contract_id, contract.client_id, contract.client_name,
                    contract.contract_type, contract.contract_name,
                    contract.status,
                    str(contract.start_date) if contract.start_date else None,
                    str(contract.end_date) if contract.end_date else None,
                    now,
                ),
            )
