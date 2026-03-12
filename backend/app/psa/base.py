"""Abstract PSA provider interface.

All PSA interactions go through this contract. Implement one class per PSA platform.
Nothing outside the provider classes should know which PSA we are using.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import (
    Category,
    Client,
    ClientContract,
    Conversation,
    PaginatedResult,
    SLAPolicy,
    Technician,
    TicketDetail,
    TicketFilter,
    WorklogEntry,
)


class PSAProvider(ABC):
    """Abstract interface for PSA integrations."""

    @abstractmethod
    async def get_tickets(self, filters: TicketFilter) -> PaginatedResult:
        """Fetch tickets with filtering and pagination."""

    @abstractmethod
    async def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        """Fetch a single ticket with full detail including conversations."""

    @abstractmethod
    async def get_ticket_conversations(self, ticket_id: str) -> list[Conversation]:
        """Fetch conversation/reply history for a ticket."""

    @abstractmethod
    async def get_technicians(self) -> list[Technician]:
        """Fetch all technicians/agents."""

    @abstractmethod
    async def get_clients(self) -> list[Client]:
        """Fetch all clients/accounts."""

    @abstractmethod
    async def get_client_contracts(self, client_id: str) -> list[ClientContract]:
        """Fetch contracts for a specific client."""

    @abstractmethod
    async def get_all_contracts(self) -> list[ClientContract]:
        """Fetch all client contracts (for bulk sync)."""

    @abstractmethod
    async def get_categories(self) -> list[Category]:
        """Fetch ticket categories and subcategories."""

    @abstractmethod
    async def get_sla_policies(self) -> list[SLAPolicy]:
        """Fetch SLA policy definitions."""

    @abstractmethod
    async def get_worklog_entries(self, ticket_id: str) -> list[WorklogEntry]:
        """Fetch time entries/worklogs for a ticket."""

    @abstractmethod
    def get_ticket_url(self, ticket_id: str) -> str:
        """Generate a direct URL to view a ticket in the PSA web UI."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the PSA name (e.g. 'SuperOps', 'HaloPSA') for display."""
