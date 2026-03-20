"""Phone sync engine: fetches call data from phone provider into SQLite."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiosqlite

from app.database import Database
from app.phone.base import PhoneProvider

logger = logging.getLogger(__name__)


class PhoneSyncEngine:
    def __init__(self, provider: PhoneProvider, db: Database, lookback_days: int = 30):
        self.provider = provider
        self.db = db
        self.lookback_days = lookback_days
        self._last_sync_time: datetime | None = None
        self._is_syncing = False

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    @property
    def last_sync_time(self) -> datetime | None:
        return self._last_sync_time

    async def sync(self) -> dict:
        """Run phone data sync."""
        if self._is_syncing:
            return {"status": "skipped", "reason": "already syncing"}

        self._is_syncing = True
        started_at = datetime.now()
        conn = await self.db.get_connection()
        errors: list[str] = []
        calls_synced = 0

        try:
            # Sync users
            try:
                users = await self.provider.get_users()
                await self._sync_users(conn, users)
                logger.info("Synced %d phone users", len(users))
            except Exception as e:
                msg = f"Failed to sync phone users: {e}"
                logger.error(msg)
                errors.append(msg)

            # Sync queues
            try:
                queues = await self.provider.get_call_queues()
                await self._sync_queues(conn, queues)
                logger.info("Synced %d call queues", len(queues))
            except Exception as e:
                msg = f"Failed to sync call queues: {e}"
                logger.error(msg)
                errors.append(msg)

            # Sync call logs
            try:
                to_date = datetime.now()
                from_date = to_date - timedelta(days=self.lookback_days)
                calls_synced = await self._sync_call_logs(conn, from_date, to_date)
                logger.info("Synced %d phone calls", calls_synced)
            except Exception as e:
                msg = f"Failed to sync call logs: {e}"
                logger.error(msg)
                errors.append(msg)

            await conn.commit()

            # Aggregate daily stats
            try:
                await self._aggregate_daily_stats(conn)
                await conn.commit()
            except Exception as e:
                msg = f"Failed to aggregate phone stats: {e}"
                logger.error(msg)
                errors.append(msg)

            self._last_sync_time = datetime.now()

        except Exception as e:
            msg = f"Phone sync failed: {e}"
            logger.error(msg)
            errors.append(msg)
            await conn.rollback()
        finally:
            self._is_syncing = False

        return {
            "status": "completed" if not errors else "completed_with_errors",
            "calls_synced": calls_synced,
            "errors": errors,
            "duration_seconds": (datetime.now() - started_at).total_seconds(),
        }

    async def _sync_call_logs(
        self, conn: aiosqlite.Connection, from_date: datetime, to_date: datetime
    ) -> int:
        """Fetch and upsert call logs."""
        total = 0
        page = 1
        max_pages = 50

        while page <= max_pages:
            result = await self.provider.get_call_logs(from_date, to_date, page)
            for call in result.items:
                now = datetime.now().isoformat()
                await conn.execute(
                    """INSERT OR REPLACE INTO phone_calls (
                        id, direction, caller_number, caller_name,
                        callee_number, callee_name,
                        start_time, answer_time, end_time,
                        duration, wait_time, hold_time, result,
                        user_id, user_email, queue_id, queue_name,
                        has_recording, has_voicemail,
                        matched_client_id, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        call.id, call.direction, call.caller_number, call.caller_name,
                        call.callee_number, call.callee_name,
                        call.start_time.isoformat(),
                        call.answer_time.isoformat() if call.answer_time else None,
                        call.end_time.isoformat(),
                        call.duration, call.wait_time, call.hold_time, call.result,
                        call.user_id, call.user_email, call.queue_id, call.queue_name,
                        1 if call.has_recording else 0,
                        1 if call.has_voicemail else 0,
                        call.client_id, now,
                    ),
                )
                total += 1

            if not result.has_more:
                break
            page += 1

        return total

    async def _sync_users(self, conn: aiosqlite.Connection, users: list) -> None:
        now = datetime.now().isoformat()
        for user in users:
            await conn.execute(
                """INSERT OR REPLACE INTO phone_users
                   (id, email, name, extension, department, status, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user.id, user.email, user.name, user.extension,
                 user.department, user.status, now),
            )

    async def _sync_queues(self, conn: aiosqlite.Connection, queues: list) -> None:
        now = datetime.now().isoformat()
        for queue in queues:
            await conn.execute(
                """INSERT OR REPLACE INTO phone_queues
                   (id, name, extension, member_count, synced_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (queue.id, queue.name, queue.extension, queue.member_count, now),
            )

    async def _aggregate_daily_stats(self, conn: aiosqlite.Connection) -> None:
        """Aggregate call data into phone_agent_daily table."""
        await conn.execute("DELETE FROM phone_agent_daily")
        await conn.execute("""
            INSERT INTO phone_agent_daily (
                date, user_id, user_email,
                total_calls, inbound_calls, outbound_calls,
                answered_calls, missed_calls, voicemail_calls,
                total_talk_seconds, total_wait_seconds, total_hold_seconds,
                avg_handle_seconds
            )
            SELECT
                DATE(start_time) as date,
                user_id,
                user_email,
                COUNT(*) as total_calls,
                SUM(CASE WHEN direction = 'inbound' THEN 1 ELSE 0 END),
                SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'missed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'voicemail' THEN 1 ELSE 0 END),
                SUM(CASE WHEN result = 'connected' THEN duration ELSE 0 END),
                SUM(wait_time),
                SUM(hold_time),
                CASE
                    WHEN SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END) > 0
                    THEN SUM(CASE WHEN result = 'connected' THEN duration ELSE 0 END)
                         / SUM(CASE WHEN result = 'connected' THEN 1 ELSE 0 END)
                    ELSE 0
                END
            FROM phone_calls
            WHERE user_id IS NOT NULL
            GROUP BY DATE(start_time), user_id
        """)
