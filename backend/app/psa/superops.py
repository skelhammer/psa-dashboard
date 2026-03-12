"""SuperOps PSA provider implementation.

All SuperOps-specific field names and API quirks are contained here.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import SuperOpsConfig
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

logger = logging.getLogger(__name__)

CLOSED_STATUSES = ["Resolved", "Closed"]
MAX_PAGES_ACTIVE = 50
MAX_PAGES_HISTORICAL = 100

# GraphQL queries
QUERY_TICKET_LIST = """
query getTicketList($input: ListInfoInput!) {
    getTicketList(input: $input) {
        tickets {
            ticketId
            displayId
            subject
            status
            priority
            technician
            requester
            client
            techGroup
            createdTime
            updatedTime
            firstResponseDueTime
            firstResponseTime
            firstResponseViolated
            resolutionDueTime
            resolutionTime
            resolutionViolated
            sla
            requestType
            source
            impact
            urgency
            category
            subcategory
            worklogTimespent
        }
        listInfo {
            page
            pageSize
            hasMore
            totalCount
        }
    }
}
"""

QUERY_TECHNICIAN_LIST = """
query getTechnicianList($input: ListInfoInput!) {
    getTechnicianList(input: $input) {
        userList {
            userId
            name
        }
        listInfo { page pageSize hasMore totalCount }
    }
}
"""

QUERY_CLIENT_LIST = """
query getClientList($input: ListInfoInput!) {
    getClientList(input: $input) {
        clients {
            accountId
            name
            stage
            status
            emailDomains
            customFields
            accountManager
            primaryContact
            hqSite
            technicianGroups
        }
        listInfo { page pageSize hasMore totalCount }
    }
}
"""

QUERY_CONTRACT_LIST = """
query getClientContractList($input: ListInfoInput) {
    getClientContractList(input: $input) {
        contracts {
            contractId
            client
            contract
            startDate
            endDate
            contractStatus
        }
        listInfo { page pageSize hasMore totalCount }
    }
}
"""

QUERY_CONVERSATION_LIST = """
query getTicketConversationList($input: TicketIdentifierInput!) {
    getTicketConversationList(input: $input) {
        conversationId
        content
        time
        type
        user {
            userId
            name
            email
        }
    }
}
"""


def _parse_datetime(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        try:
            return datetime.strptime(val, "%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            logger.warning("Could not parse datetime: %s", val)
            return None


def _parse_worklog_minutes(val: str | None) -> int:
    """Parse worklogTimespent string (e.g. '100.00') to integer minutes."""
    if not val:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _safe_str(obj: dict | None, key: str, default: str = "") -> str:
    if obj is None:
        return default
    val = obj.get(key)
    return str(val) if val is not None else default


def _safe_nested(obj: dict | None, key: str) -> dict | None:
    if obj is None:
        return None
    val = obj.get(key)
    return val if isinstance(val, dict) else None


def _map_ticket(raw: dict) -> Ticket:
    """Map SuperOps ticket fields to normalized Ticket model."""
    tech = raw.get("technician") if isinstance(raw.get("technician"), dict) else None
    requester = raw.get("requester") if isinstance(raw.get("requester"), dict) else None
    client = raw.get("client") if isinstance(raw.get("client"), dict) else None
    tech_group = raw.get("techGroup") if isinstance(raw.get("techGroup"), dict) else None
    sla = raw.get("sla") if isinstance(raw.get("sla"), dict) else None

    return Ticket(
        id=str(raw.get("ticketId", "")),
        display_id=str(raw.get("displayId", "")),
        subject=raw.get("subject", ""),
        ticket_type=raw.get("requestType", ""),
        source=raw.get("source", ""),
        client_id=_safe_str(client, "accountId") if client and "accountId" in (client or {}) else _safe_str(client, "clientId"),
        client_name=_safe_str(client, "name", "Unknown"),
        requester_id=_safe_str(requester, "userId"),
        requester_name=_safe_str(requester, "name", "Unknown"),
        tech_group_id=_safe_str(tech_group, "groupId") if tech_group else None,
        tech_group_name=_safe_str(tech_group, "name") if tech_group else None,
        technician_id=_safe_str(tech, "userId") if tech else None,
        technician_name=_safe_str(tech, "name") if tech else None,
        status=raw.get("status", "Open"),
        priority=raw.get("priority", "Medium"),
        impact=raw.get("impact"),
        urgency=raw.get("urgency"),
        category=raw.get("category"),
        subcategory=raw.get("subcategory"),
        sla_id=_safe_str(sla, "id") if sla else None,
        sla_name=_safe_str(sla, "name") if sla else None,
        created_time=_parse_datetime(raw.get("createdTime")) or datetime.now(),
        updated_time=_parse_datetime(raw.get("updatedTime")) or datetime.now(),
        first_response_due=_parse_datetime(raw.get("firstResponseDueTime")),
        first_response_time=_parse_datetime(raw.get("firstResponseTime")),
        first_response_violated=raw.get("firstResponseViolated"),
        resolution_due=_parse_datetime(raw.get("resolutionDueTime")),
        resolution_time=_parse_datetime(raw.get("resolutionTime")),
        resolution_violated=raw.get("resolutionViolated"),
        worklog_minutes=_parse_worklog_minutes(raw.get("worklogTimespent")),
    )


def _normalize_contract_type(raw_type: str | None) -> str:
    """Map SuperOps contract type strings to normalized types."""
    if not raw_type:
        return "other"
    lower = raw_type.lower()
    if "block hour" in lower or "block_hour" in lower:
        return "block_hour"
    if "block money" in lower or "block_money" in lower:
        return "block_money"
    if "hourly" in lower or "time and material" in lower:
        return "hourly"
    if "managed" in lower or "service bundle" in lower:
        return "managed"
    if "per device" in lower or "per_device" in lower:
        return "per_device"
    if "flat" in lower:
        return "flat_rate"
    return "other"


class SuperOpsProvider(PSAProvider):
    """SuperOps PSA provider using GraphQL API."""

    def __init__(self, config: SuperOpsConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json",
            "CustomerSubDomain": config.subdomain,
        }
        self._first_run_logged = False

    async def _graphql(self, query: str, variables: dict | None = None, retries: int = 3) -> dict:
        """Execute a GraphQL query with retry and backoff."""
        import asyncio

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.config.api_url,
                        json={"query": query, "variables": variables or {}},
                        headers=self.headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                    if "errors" in data:
                        logger.error("GraphQL errors: %s", data["errors"])
                        raise RuntimeError(f"GraphQL errors: {data['errors']}")

                    return data.get("data", {})
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    logger.warning("API request failed (attempt %d/%d), retrying in %ds: %s", attempt + 1, retries, wait, e)
                    await asyncio.sleep(wait)
                else:
                    raise

        return {}

    async def _paginate(self, query: str, result_key: str, items_key: str, max_pages: int = MAX_PAGES_ACTIVE, extra_input: dict | None = None) -> list[dict]:
        """Paginate through all results for a query."""
        all_items = []
        page = 1

        while page <= max_pages:
            variables = {
                "input": {
                    "page": page,
                    "pageSize": 100,
                    **(extra_input or {}),
                }
            }

            data = await self._graphql(query, variables)
            result = data.get(result_key, {})
            items = result.get(items_key, [])
            list_info = result.get("listInfo", {})

            all_items.extend(items)

            if not list_info.get("hasMore", False):
                break

            page += 1

        return all_items

    async def get_tickets(self, filters: TicketFilter) -> PaginatedResult:
        extra_input: dict = {}

        # Build condition
        if filters.exclude_statuses:
            extra_input["condition"] = {
                "attribute": "status",
                "operator": "notIncludes",
                "value": filters.exclude_statuses,
            }
        elif filters.statuses:
            extra_input["condition"] = {
                "attribute": "status",
                "operator": "includes",
                "value": filters.statuses,
            }

        extra_input["sort"] = [{"attribute": "updatedTime", "order": "DESC"}]

        if filters.updated_since:
            # For incremental sync, add updatedTime filter
            if "condition" in extra_input:
                existing = extra_input["condition"]
                extra_input["condition"] = {
                    "joinOperator": "AND",
                    "operands": [
                        existing,
                        {
                            "attribute": "updatedTime",
                            "operator": "greaterThan",
                            "value": filters.updated_since.isoformat(),
                        },
                    ],
                }
            else:
                extra_input["condition"] = {
                    "attribute": "updatedTime",
                    "operator": "greaterThan",
                    "value": filters.updated_since.isoformat(),
                }

        # For paginated single-page requests
        variables = {
            "input": {
                "page": filters.page,
                "pageSize": filters.page_size,
                **extra_input,
            }
        }

        data = await self._graphql(QUERY_TICKET_LIST, variables)
        result = data.get("getTicketList", {})

        raw_tickets = result.get("tickets", [])

        # First-run discovery logging
        if not self._first_run_logged and raw_tickets:
            logger.info("=== FIRST-RUN DISCOVERY: Sample ticket raw data ===")
            logger.info("%s", raw_tickets[0])
            self._first_run_logged = True

        tickets = [_map_ticket(t) for t in raw_tickets]
        list_info = result.get("listInfo", {})

        return PaginatedResult(
            items=tickets,
            page=list_info.get("page", filters.page),
            page_size=list_info.get("pageSize", filters.page_size),
            has_more=list_info.get("hasMore", False),
            total_count=list_info.get("totalCount", len(tickets)),
        )

    async def get_all_tickets(self, filters: TicketFilter) -> list[Ticket]:
        """Fetch ALL tickets across all pages."""
        extra_input: dict = {}
        if filters.exclude_statuses:
            extra_input["condition"] = {
                "attribute": "status",
                "operator": "notIncludes",
                "value": filters.exclude_statuses,
            }
        extra_input["sort"] = [{"attribute": "updatedTime", "order": "DESC"}]

        raw_items = await self._paginate(
            QUERY_TICKET_LIST, "getTicketList", "tickets",
            max_pages=MAX_PAGES_HISTORICAL, extra_input=extra_input,
        )
        return [_map_ticket(t) for t in raw_items]

    async def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        # Get ticket from a filtered query
        filters = TicketFilter(page=1, page_size=1)
        result = await self.get_tickets(filters)
        ticket = next((t for t in result.items if t.id == ticket_id), None)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        conversations = await self.get_ticket_conversations(ticket_id)
        return TicketDetail(ticket=ticket, conversations=conversations)

    async def get_ticket_conversations(self, ticket_id: str) -> list[Conversation]:
        variables = {"input": {"ticketId": ticket_id}}
        data = await self._graphql(QUERY_CONVERSATION_LIST, variables)
        raw_convos = data.get("getTicketConversationList", []) or []

        # First-run: log all unique conversation types
        if raw_convos:
            unique_types = set(c.get("type", "") for c in raw_convos)
            logger.info("Conversation types for ticket %s: %s", ticket_id, unique_types)

        conversations = []
        for raw in raw_convos:
            user = raw.get("user") or {}
            conversations.append(Conversation(
                conversation_id=str(raw.get("conversationId", "")),
                content=raw.get("content", ""),
                time=_parse_datetime(raw.get("time")),
                conv_type=raw.get("type", ""),
                user_id=str(user.get("userId", "")),
                user_name=user.get("name", ""),
                user_email=user.get("email", ""),
            ))

        return conversations

    async def get_technicians(self) -> list[Technician]:
        raw_items = await self._paginate(
            QUERY_TECHNICIAN_LIST, "getTechnicianList", "userList",
        )
        techs = []
        for raw in raw_items:
            name = raw.get("name", "")
            parts = name.split(" ", 1)
            techs.append(Technician(
                id=str(raw.get("userId", "")),
                first_name=parts[0] if parts else "",
                last_name=parts[1] if len(parts) > 1 else "",
            ))
        return techs

    async def get_clients(self) -> list[Client]:
        raw_items = await self._paginate(
            QUERY_CLIENT_LIST, "getClientList", "clients",
        )

        # First-run discovery logging
        if raw_items and not self._first_run_logged:
            logger.info("=== FIRST-RUN DISCOVERY: Sample client raw data ===")
            logger.info("%s", raw_items[0])

        clients = []
        for raw in raw_items:
            # Plan is stored in customFields.udf1select
            custom_fields = raw.get("customFields") or {}
            plan = custom_fields.get("udf1select") if isinstance(custom_fields, dict) else None

            clients.append(Client(
                id=str(raw.get("accountId", "")),
                name=raw.get("name", ""),
                plan=plan,
            ))
        return clients

    async def get_client_contracts(self, client_id: str) -> list[ClientContract]:
        all_contracts = await self.get_all_contracts()
        return [c for c in all_contracts if c.client_id == client_id]

    async def get_all_contracts(self) -> list[ClientContract]:
        raw_items = await self._paginate(
            QUERY_CONTRACT_LIST, "getClientContractList", "contracts",
        )

        # First-run discovery logging
        if raw_items:
            logger.info("=== FIRST-RUN DISCOVERY: Sample contract raw data ===")
            logger.info("%s", raw_items[0])

        contracts = []
        for raw in raw_items:
            client_obj = raw.get("client") or {}
            contract_obj = raw.get("contract") or {}

            # Discover contract type field (undocumented)
            contract_type_raw = contract_obj.get("type") or contract_obj.get("contractType") or ""
            logger.info("Contract %s type raw: %s, full contract obj: %s", raw.get("contractId"), contract_type_raw, contract_obj)

            contracts.append(ClientContract(
                contract_id=str(raw.get("contractId", "")),
                client_id=str(client_obj.get("accountId", client_obj.get("clientId", ""))),
                client_name=client_obj.get("name", ""),
                contract_type=_normalize_contract_type(str(contract_type_raw)),
                contract_name=contract_obj.get("name"),
                status=raw.get("contractStatus", "active").lower(),
                start_date=None,  # Parse if present
                end_date=None,
            ))
        return contracts

    async def get_categories(self) -> list[Category]:
        # getCategoryList is confirmed but not yet tested
        logger.warning("getCategoryList not yet tested; returning empty list")
        return []

    async def get_sla_policies(self) -> list[SLAPolicy]:
        # getSLAList is confirmed but not yet tested
        logger.warning("getSLAList not yet tested; returning empty list")
        return []

    async def get_worklog_entries(self, ticket_id: str) -> list[WorklogEntry]:
        # getWorklogEntries has undocumented input/output; not needed for Phase 1
        logger.warning("getWorklogEntries not implemented; using ticket-level worklogTimespent instead")
        return []

    def get_ticket_url(self, ticket_id: str) -> str:
        subdomain = self.config.subdomain
        return f"https://helpdesk.{subdomain}.com/#/tickets/{ticket_id}/ticket"

    def get_provider_name(self) -> str:
        return "SuperOps"
