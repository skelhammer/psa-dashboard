"""Zendesk REST API v2 provider implementation.

Ported from thebeacon/app/psa/zendesk.py and adapted for async httpx
and this dashboard's PSAProvider interface with normalized data models.

All Zendesk-specific field names and API quirks are contained here.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import ZendeskConfig, get_settings
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

# Zendesk priority -> normalized priority (matching SuperOps conventions)
PRIORITY_MAP = {
    "low": "Low",
    "normal": "Medium",
    "high": "High",
    "urgent": "Urgent",
}

# Zendesk status -> normalized status (matching SuperOps conventions)
STATUS_MAP = {
    "new": "Open",
    "open": "Open",
    "pending": "Waiting on Customer",
    "hold": "On Hold",
    "solved": "Resolved",
    "closed": "Closed",
}

# Fallback display names when custom statuses are not available
STATUS_DISPLAY = {
    "new": "New",
    "open": "Open",
    "pending": "Pending",
    "hold": "On-hold",
    "solved": "Solved",
    "closed": "Closed",
}

MAX_RETRIES = 3
BACKOFF_FACTOR = 1
BATCH_SIZE = 100
MAX_PAGES = 50


class ZendeskProvider(PSAProvider):
    """Zendesk REST API v2 provider (async)."""

    def __init__(self, config: ZendeskConfig):
        self.subdomain = config.subdomain
        self.email = config.email
        self.api_token = config.api_token
        self.base_url = f"https://{self.subdomain}.zendesk.com/api/v2"
        self.page_size = config.page_size or 100
        self.ticket_url_template = (
            config.ticket_url_template
            or f"https://{self.subdomain}.zendesk.com/agent/tickets/{{ticket_id}}"
        )
        self.exclude_custom_fields = config.exclude_custom_fields or []
        self._status_display_overrides = config.status_display_overrides or {}
        self.extra_agents = config.extra_agents or {}
        self.tech_merge_map = config.tech_merge_map or {}

        # Build Basic auth header: {email}/token:{api_token}
        credentials = f"{self.email}/token:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self._auth_header = f"Basic {encoded}"

        # Track endpoints that return 403 so we skip future calls
        self._forbidden_endpoints: set[str] = set()

        # Custom status labels (loaded on first use)
        self._custom_statuses: dict[int, str] | None = None

        # Shared async client (created lazily)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": self._auth_header,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _get(self, url: str, params: dict | None = None) -> dict:
        """Make a GET request with retry and rate-limit handling."""
        client = self._get_client()
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning("Zendesk rate limit hit, waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = BACKOFF_FACTOR * (2 ** attempt)
                    logger.warning("Zendesk request failed (attempt %d), retrying in %ds: %s", attempt + 1, wait, e)
                    await asyncio.sleep(wait)
                else:
                    raise
        return {}

    async def _load_custom_statuses(self) -> dict[int, str]:
        """Fetch custom status labels from Zendesk."""
        if self._custom_statuses is not None:
            return self._custom_statuses
        try:
            data = await self._get(f"{self.base_url}/custom_statuses.json")
            mapping = {}
            for s in data.get("custom_statuses", []):
                mapping[s["id"]] = s.get("agent_label", s.get("status_category", ""))
            if mapping:
                logger.info("Loaded %d Zendesk custom statuses", len(mapping))
            self._custom_statuses = mapping
            return mapping
        except Exception as e:
            logger.warning("Failed to load custom statuses: %s", e)
            self._custom_statuses = {}
            return {}

    def _resolve_status(self, ticket: dict) -> str:
        """Get the normalized status for a ticket, using custom status if available."""
        custom_id = ticket.get("custom_status_id")
        if custom_id and self._custom_statuses and custom_id in self._custom_statuses:
            label = self._custom_statuses[custom_id]
            label = self._status_display_overrides.get(label, label)
            # Try to map the custom label to a normalized status
            lower = label.lower()
            return STATUS_MAP.get(lower, label)
        raw = (ticket.get("status") or "new").lower()
        return STATUS_MAP.get(raw, raw.capitalize())

    def _resolve_display_status(self, ticket: dict) -> str:
        """Get human-readable display status (before normalization)."""
        custom_id = ticket.get("custom_status_id")
        if custom_id and self._custom_statuses and custom_id in self._custom_statuses:
            label = self._custom_statuses[custom_id]
            return self._status_display_overrides.get(label, label)
        raw = (ticket.get("status") or "new").lower()
        return STATUS_DISPLAY.get(raw, raw.capitalize())

    def _build_query(self, base_query: str) -> str:
        """Build a Zendesk search query.

        Corp tickets are no longer excluded at the API level; instead they
        are tagged with is_corp=True during normalization so the frontend
        can toggle their visibility.
        """
        return base_query

    def _check_is_corp(self, ticket: dict) -> bool:
        """Check if a ticket matches any exclude_custom_fields rule (i.e. is a Corp ticket)."""
        for rule in self.exclude_custom_fields:
            # Rule format: "custom_field_{id}:{value}"
            if ":" not in rule:
                continue
            field_key, expected_value = rule.split(":", 1)
            # field_key is like "custom_field_46556089549339"
            field_id_str = field_key.replace("custom_field_", "")
            try:
                field_id = int(field_id_str)
            except ValueError:
                continue
            for cf in ticket.get("custom_fields", []):
                if cf.get("id") == field_id:
                    if str(cf.get("value", "")).lower() == expected_value.lower():
                        return True
        return False

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse ISO 8601 datetime from Zendesk into naive local time."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            tz_name = get_settings().server.timezone
            local_tz = ZoneInfo(tz_name)
            return dt.astimezone(local_tz).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Batch fetching (ported from Beacon)
    # ------------------------------------------------------------------

    async def _batch_fetch_users(self, user_ids: set) -> dict[int, dict]:
        """Fetch multiple users by ID. Returns {id: user_dict}."""
        if not user_ids:
            return {}
        users = {}
        ids_list = list(user_ids)
        for i in range(0, len(ids_list), BATCH_SIZE):
            batch = ids_list[i : i + BATCH_SIZE]
            url = f"{self.base_url}/users/show_many.json"
            params = {"ids": ",".join(str(uid) for uid in batch)}
            try:
                data = await self._get(url, params)
                for user in data.get("users", []):
                    users[user["id"]] = user
            except Exception as e:
                logger.warning("Failed to fetch users batch: %s", e)
        # Inject or override extra_agents (also serves as name overrides)
        for agent_id, agent_name in self.extra_agents.items():
            int_id = int(agent_id) if agent_id.isdigit() else agent_id
            if int_id in users:
                users[int_id]["name"] = agent_name
            else:
                users[int_id] = {"id": int_id, "name": agent_name, "email": ""}
        return users

    async def _batch_fetch_organizations(self, org_ids: set) -> dict[int, dict]:
        """Fetch multiple organizations by ID. Returns {id: org_dict}."""
        if not org_ids:
            return {}
        if "organizations" in self._forbidden_endpoints:
            return {}
        orgs = {}
        ids_list = list(org_ids)
        for i in range(0, len(ids_list), BATCH_SIZE):
            batch = ids_list[i : i + BATCH_SIZE]
            url = f"{self.base_url}/organizations/show_many.json"
            params = {"ids": ",".join(str(oid) for oid in batch)}
            try:
                data = await self._get(url, params)
                for org in data.get("organizations", []):
                    orgs[org["id"]] = org
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.info("Organizations endpoint returned 403; skipping future calls")
                    self._forbidden_endpoints.add("organizations")
                    return {}
                logger.warning("Failed to fetch organizations batch: %s", e)
            except Exception as e:
                logger.warning("Failed to fetch organizations batch: %s", e)
        return orgs

    async def _enrich_with_metrics(self, ticket_ids: list) -> dict[int, dict]:
        """Fetch ticket metrics in bulk. Returns {ticket_id: metric_set}."""
        if not ticket_ids:
            return {}
        metrics = {}
        for i in range(0, len(ticket_ids), BATCH_SIZE):
            batch = ticket_ids[i : i + BATCH_SIZE]
            url = f"{self.base_url}/tickets/show_many.json"
            params = {
                "ids": ",".join(str(tid) for tid in batch),
                "include": "metric_sets",
            }
            try:
                data = await self._get(url, params)
                for ticket in data.get("tickets", []):
                    tid = ticket.get("id")
                    metric_set = ticket.get("metric_set")
                    if tid and metric_set:
                        metrics[tid] = metric_set
            except Exception as e:
                logger.warning("Failed to fetch ticket metrics batch: %s", e)
        return metrics

    # ------------------------------------------------------------------
    # PSAProvider interface implementation
    # ------------------------------------------------------------------

    async def get_tickets(self, filters: TicketFilter) -> PaginatedResult:
        """Fetch tickets using Zendesk Search API."""
        await self._load_custom_statuses()

        # Build search query based on filters
        if filters.ticket_ids:
            # Fetch specific tickets by ID
            tickets = []
            for tid in filters.ticket_ids:
                try:
                    data = await self._get(f"{self.base_url}/tickets/{tid}.json")
                    raw_ticket = data.get("ticket")
                    if raw_ticket:
                        tickets.append(raw_ticket)
                except Exception as e:
                    logger.warning("Failed to fetch ticket %s: %s", tid, e)
            # Sideload users and orgs
            user_ids = set()
            org_ids = set()
            for t in tickets:
                if t.get("requester_id"):
                    user_ids.add(t["requester_id"])
                if t.get("assignee_id"):
                    user_ids.add(t["assignee_id"])
                if t.get("organization_id"):
                    org_ids.add(t["organization_id"])
            users = await self._batch_fetch_users(user_ids)
            orgs = await self._batch_fetch_organizations(org_ids)
            items = [self._ticket_to_model(t, users, orgs) for t in tickets]
            return PaginatedResult(items=items, page=1, page_size=len(items), has_more=False, total_count=len(items))

        if filters.updated_since:
            # Incremental: search for recently updated tickets
            since_iso = filters.updated_since.isoformat()
            query = self._build_query(f"type:ticket updated>{since_iso[:10]}")
        elif filters.exclude_statuses:
            query = self._build_query("type:ticket status<solved")
        else:
            query = self._build_query("type:ticket")

        params = {
            "query": query,
            "page": filters.page,
            "per_page": min(filters.page_size, 100),
            "sort_by": "updated_at",
            "sort_order": "desc",
        }

        url = f"{self.base_url}/search.json"
        data = await self._get(url, params)
        results = data.get("results", [])
        next_page = data.get("next_page")
        has_more = next_page is not None

        # Sideload users and organizations
        user_ids: set = set()
        org_ids: set = set()
        for ticket in results:
            if ticket.get("requester_id"):
                user_ids.add(ticket["requester_id"])
            if ticket.get("assignee_id"):
                user_ids.add(ticket["assignee_id"])
            if ticket.get("organization_id"):
                org_ids.add(ticket["organization_id"])
        users = await self._batch_fetch_users(user_ids)
        orgs = await self._batch_fetch_organizations(org_ids)

        # Enrich with metrics for SLA data
        ticket_ids_for_metrics = [t["id"] for t in results if t.get("id")]
        metrics = await self._enrich_with_metrics(ticket_ids_for_metrics)

        items = [self._ticket_to_model(t, users, orgs, metrics) for t in results]
        return PaginatedResult(
            items=items,
            page=filters.page,
            page_size=filters.page_size,
            has_more=has_more,
            total_count=data.get("count", len(items)),
        )

    def _ticket_to_model(
        self,
        ticket: dict,
        users: dict | None = None,
        orgs: dict | None = None,
        metrics: dict | None = None,
    ) -> Ticket:
        """Convert a raw Zendesk ticket dict to the normalized Ticket model."""
        users = users or {}
        orgs = orgs or {}
        metrics = metrics or {}

        priority_raw = (ticket.get("priority") or "normal").lower()
        priority = PRIORITY_MAP.get(priority_raw, "Medium")
        status = self._resolve_status(ticket)

        assignee_id = ticket.get("assignee_id")
        assignee = users.get(assignee_id, {}) if assignee_id else {}
        requester_id = ticket.get("requester_id")
        requester = users.get(requester_id, {}) if requester_id else {}
        org_id = ticket.get("organization_id")
        org = orgs.get(org_id, {}) if org_id else {}

        created_time = self._parse_datetime(ticket.get("created_at")) or datetime.now()
        updated_time = self._parse_datetime(ticket.get("updated_at")) or datetime.now()

        # SLA data from ticket metrics
        metric_set = metrics.get(ticket.get("id"), {})
        first_response_time = None
        resolution_time = None
        first_response_violated = None
        resolution_violated = None

        if metric_set:
            reply_time = metric_set.get("reply_time_in_minutes", {})
            if reply_time and reply_time.get("calendar") is not None:
                try:
                    fr_dt = created_time + timedelta(minutes=reply_time["calendar"])
                    first_response_time = fr_dt
                except (ValueError, TypeError):
                    pass

            solved_at = metric_set.get("solved_at")
            if solved_at:
                resolution_time = self._parse_datetime(solved_at)

        # Worklog hours: only read from a specific configured field ID
        # (Zendesk has no built-in time tracking; it depends on apps/custom fields)
        worklog_hours = 0.0

        group_id = ticket.get("group_id")

        return Ticket(
            id=str(ticket.get("id", "")),
            display_id=str(ticket.get("id", "")),
            subject=ticket.get("subject") or "No Subject",
            ticket_type=ticket.get("type") or "",
            source=(ticket.get("via", {}).get("channel") or ""),
            client_id=str(org_id) if org_id else "",
            client_name=org.get("name", "") if org else "",
            requester_id=str(requester_id) if requester_id else "",
            requester_name=requester.get("name", "Unknown") if requester else "Unknown",
            tech_group_id=str(group_id) if group_id else None,
            tech_group_name=None,
            technician_id=str(assignee_id) if assignee_id else None,
            technician_name=assignee.get("name") if assignee else None,
            status=status,
            priority=priority,
            category=None,
            created_time=created_time,
            updated_time=updated_time,
            first_response_due=self._parse_datetime(ticket.get("due_at")),
            first_response_time=first_response_time,
            first_response_violated=first_response_violated,
            resolution_due=self._parse_datetime(ticket.get("due_at")),
            resolution_time=resolution_time,
            resolution_violated=resolution_violated,
            worklog_hours=worklog_hours,
            is_corp=self._check_is_corp(ticket),
        )

    async def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        """Fetch a single ticket with conversations."""
        await self._load_custom_statuses()
        data = await self._get(f"{self.base_url}/tickets/{ticket_id}.json")
        raw_ticket = data.get("ticket", {})

        user_ids = set()
        if raw_ticket.get("requester_id"):
            user_ids.add(raw_ticket["requester_id"])
        if raw_ticket.get("assignee_id"):
            user_ids.add(raw_ticket["assignee_id"])
        org_ids = {raw_ticket["organization_id"]} if raw_ticket.get("organization_id") else set()

        users = await self._batch_fetch_users(user_ids)
        orgs = await self._batch_fetch_organizations(org_ids)
        metrics = await self._enrich_with_metrics([raw_ticket["id"]])

        ticket = self._ticket_to_model(raw_ticket, users, orgs, metrics)
        conversations = await self.get_ticket_conversations(ticket_id)
        return TicketDetail(ticket=ticket, conversations=conversations)

    async def get_ticket_conversations(self, ticket_id: str) -> list[Conversation]:
        """Fetch comments for a ticket."""
        url = f"{self.base_url}/tickets/{ticket_id}/comments.json"
        try:
            data = await self._get(url)
        except Exception as e:
            logger.warning("Failed to fetch comments for ticket %s: %s", ticket_id, e)
            return []

        comments = data.get("comments", [])
        if not comments:
            return []

        # Get requester_id to determine reply types
        requester_id = None
        try:
            ticket_data = await self._get(f"{self.base_url}/tickets/{ticket_id}.json")
            requester_id = ticket_data.get("ticket", {}).get("requester_id")
        except Exception:
            pass

        result = []
        for comment in comments:
            author_id = comment.get("author_id")
            is_requester = requester_id and author_id == requester_id
            conv_type = "REQ_REPLY" if is_requester else "AGENT_REPLY"

            result.append(Conversation(
                conversation_id=str(comment.get("id", "")),
                content=comment.get("body", ""),
                time=self._parse_datetime(comment.get("created_at")),
                conv_type=conv_type,
                user_id=str(author_id) if author_id else "",
            ))
        return result

    async def get_technicians(self) -> list[Technician]:
        """Fetch agents from Zendesk via Search API."""
        techs = []
        page = 1
        while page <= MAX_PAGES:
            url = f"{self.base_url}/search.json"
            params = {
                "query": "type:user role:agent",
                "page": page,
                "per_page": min(self.page_size, 100),
            }
            data = await self._get(url, params)
            users = data.get("results", [])

            for user in users:
                user_id = user.get("id")
                name = user.get("name", "")
                if user_id and name:
                    parts = name.split(" ", 1)
                    techs.append(Technician(
                        id=str(user_id),
                        first_name=parts[0],
                        last_name=parts[1] if len(parts) > 1 else "",
                        email=user.get("email", ""),
                        role="agent",
                    ))

            next_page = data.get("next_page")
            if not next_page:
                break
            page += 1

        # Add extra_agents that aren't returned by the search API
        fetched_ids = {t.id for t in techs}
        for agent_id, agent_name in self.extra_agents.items():
            if agent_id not in fetched_ids:
                parts = agent_name.split(" ", 1)
                techs.append(Technician(
                    id=agent_id,
                    first_name=parts[0],
                    last_name=parts[1] if len(parts) > 1 else "",
                    email="",
                    role="agent",
                ))

        return techs

    async def get_clients(self) -> list[Client]:
        """Fetch organizations from Zendesk."""
        clients = []
        page = 1
        while page <= MAX_PAGES:
            url = f"{self.base_url}/organizations.json"
            params = {"page": page, "per_page": min(self.page_size, 100)}
            try:
                data = await self._get(url, params)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.info("Organizations endpoint returned 403; using search fallback")
                    self._forbidden_endpoints.add("organizations")
                    break
                raise

            for org in data.get("organizations", []):
                clients.append(Client(
                    id=str(org["id"]),
                    name=org.get("name", ""),
                    stage="Active",
                ))

            next_page = data.get("next_page")
            if not next_page:
                break
            page += 1

        return clients

    async def get_client_contracts(self, client_id: str) -> list[ClientContract]:
        """Zendesk does not have a contracts concept."""
        return []

    async def get_all_contracts(self) -> list[ClientContract]:
        """Zendesk does not have a contracts concept."""
        return []

    async def get_categories(self) -> list[Category]:
        """Return categories derived from common tags (best effort)."""
        return []

    async def get_sla_policies(self) -> list[SLAPolicy]:
        """Fetch SLA policies from Zendesk."""
        try:
            data = await self._get(f"{self.base_url}/slas/policies.json")
            policies = []
            for p in data.get("sla_policies", []):
                policies.append(SLAPolicy(
                    id=str(p["id"]),
                    name=p.get("title", ""),
                ))
            return policies
        except Exception as e:
            logger.warning("Failed to fetch SLA policies: %s", e)
            return []

    async def get_worklog_entries(self, ticket_id: str) -> list[WorklogEntry]:
        """Zendesk time tracking is via custom fields, not discrete entries."""
        return []

    def get_ticket_url(self, ticket_id: str) -> str:
        """Generate URL to view a ticket in Zendesk."""
        return self.ticket_url_template.replace("{ticket_id}", str(ticket_id))

    def get_provider_name(self) -> str:
        return "Zendesk"
