"""Multi-provider sync manager.

Coordinates multiple SyncEngine instances (one per PSA provider),
running them sequentially to avoid SQLite write contention.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.sync.engine import SyncEngine

logger = logging.getLogger(__name__)


class MultiProviderSyncManager:
    def __init__(self, engines: dict[str, SyncEngine]):
        self.engines = engines

    @property
    def is_syncing(self) -> bool:
        return any(e.is_syncing for e in self.engines.values())

    @property
    def last_sync_time(self) -> datetime | None:
        times = [e.last_sync_time for e in self.engines.values() if e.last_sync_time]
        return min(times) if times else None

    @property
    def provider_names(self) -> list[str]:
        return list(self.engines.keys())

    def get_engine(self, provider_name: str) -> SyncEngine | None:
        return self.engines.get(provider_name)

    async def full_sync_all(self) -> dict:
        """Run full sync for all providers sequentially."""
        results = {}
        for name, engine in self.engines.items():
            logger.info("Running full sync for provider: %s", name)
            result = await engine.full_sync()
            results[name] = result
        return {
            "status": "completed",
            "providers": results,
        }

    async def incremental_sync_all(self) -> dict:
        """Run incremental sync for all providers sequentially."""
        results = {}
        for name, engine in self.engines.items():
            result = await engine.incremental_sync()
            results[name] = result
        return {
            "status": "completed",
            "providers": results,
        }

    async def sync_provider(self, provider_name: str) -> dict:
        """Trigger sync for a single provider."""
        engine = self.engines.get(provider_name)
        if not engine:
            return {"status": "error", "reason": f"Unknown provider: {provider_name}"}
        if engine.last_sync_time is None:
            return await engine.full_sync()
        return await engine.incremental_sync()
