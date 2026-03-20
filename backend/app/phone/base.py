"""Abstract phone provider interface.

All phone integrations go through this contract. Implement one class per phone platform.
Nothing outside the provider classes should know which phone system we are using.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.phone.models import Call, CallQueue, PaginatedCalls, PhoneUser, Voicemail


class PhoneProvider(ABC):
    """Abstract interface for phone system integrations."""

    @abstractmethod
    async def get_call_logs(
        self, from_date: datetime, to_date: datetime, page: int = 1
    ) -> PaginatedCalls:
        """Fetch call logs for a date range with pagination."""

    @abstractmethod
    async def get_users(self) -> list[PhoneUser]:
        """Fetch all phone system users."""

    @abstractmethod
    async def get_call_queues(self) -> list[CallQueue]:
        """Fetch all call queues."""

    @abstractmethod
    async def get_queue_calls(
        self, queue_id: str, from_date: datetime, to_date: datetime
    ) -> list[Call]:
        """Fetch calls for a specific queue."""

    @abstractmethod
    async def get_voicemails(self, user_id: str) -> list[Voicemail]:
        """Fetch voicemails for a specific user."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the phone provider name for display."""
