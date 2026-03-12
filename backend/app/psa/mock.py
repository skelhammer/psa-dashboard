"""Mock PSA provider for testing and frontend development.

Returns static test data for 4 techs, 5 clients, and ~25 tickets.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import (
    Category,
    Client,
    ClientContract,
    Conversation,
    PaginatedResult,
    SLAPolicy,
    Technician,
    Ticket,
    TicketDetail,
    TicketFilter,
    WorklogEntry,
)
from app.psa.base import PSAProvider

_NOW = datetime.now()
_HOUR = timedelta(hours=1)
_DAY = timedelta(days=1)

MOCK_TECHNICIANS = [
    Technician(id="t1", first_name="Troy", last_name="Anderson", email="troy@integotec.com", role="Lead"),
    Technician(id="t2", first_name="Mike", last_name="Chen", email="mike@integotec.com", role="Technician"),
    Technician(id="t3", first_name="Sarah", last_name="Johnson", email="sarah@integotec.com", role="Technician"),
    Technician(id="t4", first_name="James", last_name="Wilson", email="james@integotec.com", role="Technician"),
]

MOCK_CLIENTS = [
    Client(id="c1", name="Acme Corp"),
    Client(id="c2", name="River City Dental"),
    Client(id="c3", name="Douglas County"),
    Client(id="c4", name="Umpqua Bank"),
    Client(id="c5", name="Roseburg Forest Products"),
]

MOCK_CONTRACTS = [
    ClientContract(contract_id="ct1", client_id="c1", client_name="Acme Corp", contract_type="hourly", status="active"),
    ClientContract(contract_id="ct2", client_id="c2", client_name="River City Dental", contract_type="managed", status="active"),
    ClientContract(contract_id="ct3", client_id="c3", client_name="Douglas County", contract_type="block_hour", status="active"),
    ClientContract(contract_id="ct4", client_id="c4", client_name="Umpqua Bank", contract_type="managed", status="active"),
    ClientContract(contract_id="ct5", client_id="c5", client_name="Roseburg Forest Products", contract_type="hourly", status="active"),
]


def _ticket(
    tid: int,
    subject: str,
    client_idx: int = 0,
    tech_idx: int | None = 0,
    status: str = "Open",
    priority: str = "Medium",
    age_hours: float = 24,
    worklog: int = 0,
    sla_name: str | None = "Standard SLA",
    fr_due_hours: float | None = 4,
    res_due_hours: float | None = 24,
    fr_violated: bool | None = None,
    res_violated: bool | None = None,
    fr_time_hours: float | None = None,
    res_time_hours: float | None = None,
    source: str = "Email",
    category: str | None = "Hardware",
    subcategory: str | None = None,
) -> Ticket:
    created = _NOW - timedelta(hours=age_hours)
    client = MOCK_CLIENTS[client_idx]
    tech = MOCK_TECHNICIANS[tech_idx] if tech_idx is not None else None
    return Ticket(
        id=f"tk{tid}",
        display_id=f"TK-{tid:04d}",
        subject=subject,
        ticket_type="Incident",
        source=source,
        client_id=client.id,
        client_name=client.name,
        requester_id=f"req{tid}",
        requester_name=f"User {tid}",
        tech_group_id="6410137295585656832",
        tech_group_name="Tier 1 Support",
        technician_id=tech.id if tech else None,
        technician_name=f"{tech.first_name} {tech.last_name}" if tech else None,
        status=status,
        priority=priority,
        category=category,
        subcategory=subcategory,
        sla_name=sla_name,
        created_time=created,
        updated_time=created + timedelta(hours=age_hours * 0.5),
        first_response_due=created + timedelta(hours=fr_due_hours) if fr_due_hours else None,
        first_response_time=created + timedelta(hours=fr_time_hours) if fr_time_hours else None,
        first_response_violated=fr_violated,
        resolution_due=created + timedelta(hours=res_due_hours) if res_due_hours else None,
        resolution_time=created + timedelta(hours=res_time_hours) if res_time_hours else None,
        resolution_violated=res_violated,
        worklog_minutes=worklog,
    )


MOCK_TICKETS = [
    # Unassigned tickets
    _ticket(1, "Printer not working in conference room", client_idx=0, tech_idx=None, priority="High", age_hours=2),
    _ticket(2, "New employee laptop setup", client_idx=2, tech_idx=None, priority="Medium", age_hours=6, source="Portal"),

    # SLA violated (still open)
    _ticket(3, "Email server down", client_idx=3, tech_idx=0, priority="Critical", age_hours=48, fr_violated=True, res_violated=True, fr_time_hours=1, worklog=60),
    _ticket(4, "VPN connection failing for remote users", client_idx=1, tech_idx=1, priority="High", age_hours=30, fr_violated=False, res_violated=True, fr_time_hours=0.5, worklog=45),

    # SLA breaching soon (due within 30 min)
    _ticket(5, "Outlook keeps crashing", client_idx=0, tech_idx=2, priority="Medium", age_hours=3.5, fr_due_hours=4, fr_time_hours=1),
    _ticket(6, "Cannot access shared drive", client_idx=4, tech_idx=0, priority="High", age_hours=22, res_due_hours=24, fr_time_hours=0.5, worklog=30),

    # Awaiting tech reply (customer replied, tech hasn't)
    _ticket(7, "Slow computer performance", client_idx=2, tech_idx=1, priority="Low", age_hours=72, worklog=15, status="Customer Replied"),
    _ticket(8, "Monitor flickering", client_idx=0, tech_idx=3, priority="Medium", age_hours=48, worklog=10, status="Customer Replied"),

    # Stale tickets (no update in 3+ days)
    _ticket(9, "Software license renewal", client_idx=1, tech_idx=2, priority="Low", age_hours=120, worklog=0),
    _ticket(10, "Backup job review", client_idx=3, tech_idx=3, priority="Low", age_hours=168, worklog=0),

    # Normal open tickets
    _ticket(11, "Password reset for 3 users", client_idx=0, tech_idx=0, priority="Low", age_hours=4, worklog=15, fr_time_hours=0.5),
    _ticket(12, "Install Adobe Acrobat on workstation", client_idx=2, tech_idx=1, priority="Low", age_hours=8, worklog=20, fr_time_hours=1),
    _ticket(13, "Network switch replacement", client_idx=4, tech_idx=2, priority="High", age_hours=12, worklog=45, fr_time_hours=0.5),
    _ticket(14, "Setup MFA for new department", client_idx=3, tech_idx=0, priority="Medium", age_hours=16, worklog=30, fr_time_hours=2),
    _ticket(15, "Firewall rule change request", client_idx=1, tech_idx=3, priority="Medium", age_hours=24, worklog=0, fr_time_hours=3),

    # Waiting on customer/third party
    _ticket(16, "Server migration planning", client_idx=4, tech_idx=0, priority="Medium", age_hours=96, status="Waiting on Customer", worklog=120),
    _ticket(17, "ISP circuit upgrade coordination", client_idx=3, tech_idx=1, priority="Medium", age_hours=72, status="Waiting on third party", worklog=30),

    # Recently resolved (for metrics)
    _ticket(18, "Wireless AP replacement", client_idx=0, tech_idx=2, priority="Medium", age_hours=48, status="Resolved", worklog=90, fr_time_hours=0.5, res_time_hours=36),
    _ticket(19, "Domain join failure", client_idx=2, tech_idx=3, priority="High", age_hours=24, status="Resolved", worklog=60, fr_time_hours=0.25, res_time_hours=12),
    _ticket(20, "Printer driver update", client_idx=1, tech_idx=0, priority="Low", age_hours=12, status="Closed", worklog=15, fr_time_hours=1, res_time_hours=6),

    # Billable client tickets with no worklog (billing flags)
    _ticket(21, "Projector not connecting", client_idx=0, tech_idx=1, priority="Low", age_hours=36, status="Resolved", worklog=0, fr_time_hours=2, res_time_hours=24),
    _ticket(22, "UPS battery replacement", client_idx=4, tech_idx=2, priority="Medium", age_hours=60, status="Resolved", worklog=0, fr_time_hours=1, res_time_hours=48),

    # Under investigation
    _ticket(23, "Intermittent network drops", client_idx=3, tech_idx=0, priority="High", age_hours=36, status="Under Investigation", worklog=90, fr_time_hours=0.5),
    _ticket(24, "Database performance issues", client_idx=4, tech_idx=3, priority="Critical", age_hours=8, worklog=30, fr_time_hours=0.25),
    _ticket(25, "Spam filter misconfiguration", client_idx=1, tech_idx=2, priority="Medium", age_hours=20, worklog=25, fr_time_hours=1),
]

MOCK_CONVERSATIONS: dict[str, list[Conversation]] = {
    "tk7": [
        Conversation(conversation_id="conv1", conv_type="TECH_REPLY", time=_NOW - 60 * _HOUR, user_name="Mike Chen"),
        Conversation(conversation_id="conv2", conv_type="REQ_REPLY", time=_NOW - 48 * _HOUR, user_name="User 7"),
    ],
    "tk8": [
        Conversation(conversation_id="conv3", conv_type="TECH_REPLY", time=_NOW - 36 * _HOUR, user_name="James Wilson"),
        Conversation(conversation_id="conv4", conv_type="REQ_REPLY", time=_NOW - 24 * _HOUR, user_name="User 8"),
    ],
}


class MockProvider(PSAProvider):
    """Mock PSA provider for testing without a live PSA connection."""

    async def get_tickets(self, filters: TicketFilter) -> PaginatedResult:
        tickets = list(MOCK_TICKETS)

        if filters.exclude_statuses:
            tickets = [t for t in tickets if t.status not in filters.exclude_statuses]
        if filters.statuses:
            tickets = [t for t in tickets if t.status in filters.statuses]
        if filters.client_id:
            tickets = [t for t in tickets if t.client_id == filters.client_id]
        if filters.technician_id:
            tickets = [t for t in tickets if t.technician_id == filters.technician_id]
        if filters.updated_since:
            tickets = [t for t in tickets if t.updated_time >= filters.updated_since]

        start = (filters.page - 1) * filters.page_size
        end = start + filters.page_size
        page_items = tickets[start:end]

        return PaginatedResult(
            items=page_items,
            page=filters.page,
            page_size=filters.page_size,
            has_more=end < len(tickets),
            total_count=len(tickets),
        )

    async def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        ticket = next((t for t in MOCK_TICKETS if t.id == ticket_id), None)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        convos = MOCK_CONVERSATIONS.get(ticket_id, [])
        return TicketDetail(ticket=ticket, conversations=convos)

    async def get_ticket_conversations(self, ticket_id: str) -> list[Conversation]:
        return MOCK_CONVERSATIONS.get(ticket_id, [])

    async def get_technicians(self) -> list[Technician]:
        return list(MOCK_TECHNICIANS)

    async def get_clients(self) -> list[Client]:
        return list(MOCK_CLIENTS)

    async def get_client_contracts(self, client_id: str) -> list[ClientContract]:
        return [c for c in MOCK_CONTRACTS if c.client_id == client_id]

    async def get_all_contracts(self) -> list[ClientContract]:
        return list(MOCK_CONTRACTS)

    async def get_categories(self) -> list[Category]:
        return [
            Category(id="cat1", name="Hardware", subcategories=["Printer", "Monitor", "Laptop", "Network"]),
            Category(id="cat2", name="Software", subcategories=["Installation", "Update", "License", "Configuration"]),
            Category(id="cat3", name="Network", subcategories=["Connectivity", "VPN", "Firewall", "Switch"]),
            Category(id="cat4", name="Security", subcategories=["MFA", "Spam", "Access Control"]),
            Category(id="cat5", name="Server", subcategories=["Backup", "Migration", "Performance"]),
        ]

    async def get_sla_policies(self) -> list[SLAPolicy]:
        return [
            SLAPolicy(id="sla1", name="Standard SLA"),
            SLAPolicy(id="sla2", name="Priority SLA"),
        ]

    async def get_worklog_entries(self, ticket_id: str) -> list[WorklogEntry]:
        return []

    def get_ticket_url(self, ticket_id: str) -> str:
        return f"https://mock-psa.example.com/tickets/{ticket_id}"

    def get_provider_name(self) -> str:
        return "Mock PSA"
