"""Background sync scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.sync.engine import SyncEngine

logger = logging.getLogger(__name__)


class SyncScheduler:
    def __init__(self, engine: SyncEngine, interval_minutes: int = 15):
        self.engine = engine
        self.interval_minutes = interval_minutes
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        """Start the background sync loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Sync scheduler started (interval: %d minutes)", self.interval_minutes)

    async def stop(self):
        """Stop the background sync loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sync scheduler stopped")

    async def trigger_sync(self) -> dict:
        """Trigger an immediate sync (full if first run, incremental otherwise)."""
        if self.engine.last_sync_time is None:
            return await self.engine.full_sync()
        return await self.engine.incremental_sync()

    async def trigger_full_sync(self) -> dict:
        """Trigger an immediate full sync (re-fetches all tickets, cleans up deleted)."""
        return await self.engine.full_sync()

    async def _loop(self):
        """Background loop that runs sync at configured intervals."""
        # Run initial sync immediately
        try:
            logger.info("Running initial full sync...")
            result = await self.engine.full_sync()
            logger.info("Initial sync result: %s", result)
        except Exception as e:
            logger.error("Initial sync failed: %s", e)

        while self._running:
            try:
                await asyncio.sleep(self.interval_minutes * 60)
                if not self._running:
                    break

                # Run a full sync at midnight to clean up deleted tickets
                now = datetime.now()
                if now.hour == 0 and now.minute < self.interval_minutes:
                    logger.info("Running nightly full sync...")
                    result = await self.engine.full_sync()
                    logger.info("Nightly full sync result: %s", result)
                else:
                    logger.info("Running scheduled incremental sync...")
                    result = await self.engine.incremental_sync()
                    logger.info("Scheduled sync result: %s", result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduled sync failed: %s", e)
