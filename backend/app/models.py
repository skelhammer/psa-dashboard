"""PSA-agnostic normalized data models.

Every PSA provider maps its platform-specific fields into these models.
Nothing outside the provider classes should reference PSA-specific field names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Ticket:
    id: str
    display_id: str
    subject: str
    ticket_type: str = ""
    source: str = ""
    client_id: str = ""
    client_name: str = ""
    site_id: str | None = None
    site_name: str | None = None
    requester_id: str = ""
    requester_name: str = "Unknown"
    tech_group_id: str | None = None
    tech_group_name: str | None = None
    technician_id: str | None = None
    technician_name: str | None = None
    status: str = "Open"
    priority: str = "Medium"
    impact: str | None = None
    urgency: str | None = None
    category: str | None = None
    subcategory: str | None = None
    sla_id: str | None = None
    sla_name: str | None = None
    created_time: datetime = field(default_factory=datetime.now)
    updated_time: datetime = field(default_factory=datetime.now)
    first_response_due: datetime | None = None
    first_response_time: datetime | None = None
    first_response_violated: bool | None = None
    resolution_due: datetime | None = None
    resolution_time: datetime | None = None
    resolution_violated: bool | None = None
    worklog_hours: float = 0
    is_corp: bool = False
    fcr: bool = False


@dataclass
class Technician:
    id: str
    first_name: str
    last_name: str
    email: str = ""
    role: str = ""


@dataclass
class Client:
    id: str
    name: str
    plan: str | None = None
    stage: str | None = None
    status: str | None = None
    profit_type: str | None = None
    account_number: str | None = None


@dataclass
class ClientContract:
    contract_id: str
    client_id: str
    client_name: str
    contract_type: str = "other"
    contract_name: str | None = None
    status: str = "active"
    start_date: date | None = None
    end_date: date | None = None


@dataclass
class Conversation:
    conversation_id: str = ""
    content: str = ""
    time: datetime | None = None
    conv_type: str = ""
    user_id: str = ""
    user_name: str = ""
    user_email: str = ""


@dataclass
class Category:
    id: str
    name: str
    subcategories: list[str] = field(default_factory=list)


@dataclass
class SLAPolicy:
    id: str
    name: str


@dataclass
class WorklogEntry:
    id: str
    ticket_id: str
    technician_id: str = ""
    technician_name: str = ""
    minutes: int = 0
    description: str = ""
    created_time: datetime | None = None


@dataclass
class TicketFilter:
    """Filter criteria for fetching tickets from the PSA."""
    statuses: list[str] | None = None
    exclude_statuses: list[str] | None = None
    updated_since: datetime | None = None
    client_id: str | None = None
    technician_id: str | None = None
    ticket_ids: list[str] | None = None
    page: int = 1
    page_size: int = 100


@dataclass
class PaginatedResult:
    items: list = field(default_factory=list)
    page: int = 1
    page_size: int = 100
    has_more: bool = False
    total_count: int = 0


@dataclass
class TicketDetail:
    """Extended ticket with conversation data."""
    ticket: Ticket
    conversations: list[Conversation] = field(default_factory=list)
