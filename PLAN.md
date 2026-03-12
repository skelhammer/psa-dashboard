# PSA Manager Metrics Dashboard -- Build Plan

## Project Overview

Build a brand new web-based manager dashboard for a small MSP. This tool is for the helpdesk lead to track technician performance, SLA compliance, ticket volume trends, per-client breakdowns, billing compliance, and operational health. The helpdesk lead reports to the CEO and Operations Manager, who both want regular visibility into service desk performance. This dashboard is the single source of truth for that reporting chain.

This is a greenfield application built from scratch. A separate internal project already has a working SuperOps API integration. The proven GraphQL queries, field names, auth patterns, and instance-specific IDs from that project are documented in the "Proven SuperOps API Reference" section below. Use those as the reference for the SuperOpsProvider implementation.

### Team Context

The active service desk team is 4 technicians (including the helpdesk lead). This is a small team; individual performance is highly visible, every ticket matters, and there's no room to hide inefficiency. The dashboard audience is:
- **Helpdesk Lead:** Daily operational use. Needs to see what's about to breach SLA, what's stale, who's overloaded, what's unbilled, and what the team should work on next.
- **CEO and Ops Manager:** Weekly/monthly rollup views. Want high-level KPIs, trend lines, client health, and billing compliance. They need aggregated performance data, not individual ticket details.

---

## CRITICAL: PSA Abstraction Layer

**We are currently on SuperOps PSA but are actively evaluating HaloPSA as a replacement.** The codebase MUST be architected so that swapping the PSA backend is a contained change, not a full rewrite.

### Architecture Pattern: Provider Adapter

Implement a **PSA Provider interface** (abstract base class or protocol in Python) that defines the contract for all PSA interactions. Then implement a **SuperOpsProvider** class that fulfills that contract using the SuperOps GraphQL API. When we migrate to HaloPSA, we write a **HaloPSAProvider** class that fulfills the same contract, change a config value, and everything else stays untouched.

```
PSA Provider Interface (abstract)
    |
    |-- SuperOpsProvider (current, uses GraphQL)
    |-- HaloPSAProvider  (future, uses REST)
    |
    v
Sync Engine (calls provider interface methods)
    |
    v
SQLite Database (PSA-agnostic normalized schema)
    |
    v
Backend API (queries SQLite, computes metrics)
    |
    v
React Frontend (talks to backend API only)
```

### Provider Interface Methods

Each method returns data in a **normalized, PSA-agnostic format** (Python dataclasses or dicts with consistent field names). The provider handles all translation from PSA-specific field names and API quirks.

```python
class PSAProvider(ABC):
    """Abstract interface for PSA integrations. Implement one per PSA platform."""

    @abstractmethod
    async def get_tickets(self, filters: TicketFilter) -> PaginatedResult[Ticket]:
        """Fetch tickets with filtering and pagination."""

    @abstractmethod
    async def get_ticket_detail(self, ticket_id: str) -> TicketDetail:
        """Fetch a single ticket with full detail including conversations."""

    @abstractmethod
    async def get_ticket_conversations(self, ticket_id: str) -> list[Conversation]:
        """Fetch conversation/reply history for FCR and awaiting-tech-reply detection."""

    @abstractmethod
    async def get_technicians(self) -> list[Technician]:
        """Fetch all technicians/agents."""

    @abstractmethod
    async def get_clients(self) -> list[Client]:
        """Fetch all clients/accounts."""

    @abstractmethod
    async def get_client_contracts(self, client_id: str) -> list[ClientContract]:
        """Fetch contracts for a client (needed for billing type detection)."""

    @abstractmethod
    async def get_all_contracts(self) -> list[ClientContract]:
        """Fetch all client contracts (for bulk sync of billing types)."""

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
        """Generate a direct URL to view a ticket in the PSA's web UI."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the PSA name (e.g. 'SuperOps', 'HaloPSA') for display."""
```

### Normalized Data Models

PSA-agnostic dataclasses the entire app uses. Provider maps PSA-specific fields to these.

```python
@dataclass
class Ticket:
    id: str                     # PSA's internal ID
    display_id: str             # Human-readable ticket number
    subject: str
    ticket_type: str            # Incident, Service Request, etc.
    source: str                 # Email, Portal, Phone, etc.
    client_id: str
    client_name: str
    site_id: str | None
    site_name: str | None
    requester_id: str
    requester_name: str
    tech_group_id: str | None
    tech_group_name: str | None
    technician_id: str | None
    technician_name: str | None
    status: str
    priority: str
    impact: str | None
    urgency: str | None
    category: str | None
    subcategory: str | None
    sla_id: str | None
    sla_name: str | None
    created_time: datetime
    updated_time: datetime
    first_response_due: datetime | None
    first_response_time: datetime | None
    first_response_violated: bool | None
    resolution_due: datetime | None
    resolution_time: datetime | None
    resolution_violated: bool | None
    worklog_minutes: int        # Total logged time in minutes (from worklogTimespent on ticket object, no per-ticket API call needed)

@dataclass
class ClientContract:
    contract_id: str
    client_id: str
    client_name: str
    contract_type: str          # Normalized: "hourly", "block_hour", "block_money",
                                # "managed", "per_device", "flat_rate", "other"
    contract_name: str | None
    status: str                 # "active", "draft", "expired", etc.
    start_date: date | None
    end_date: date | None
```

### Provider Configuration

```yaml
# config.yaml
psa:
  provider: superops            # Change to "halopsa" when migrating
  superops:
    api_url: https://api.superops.ai/msp
    api_token: <token>
    subdomain: <subdomain>
  halopsa:                      # Pre-stub for future use
    api_url: https://<instance>.halopsa.com/api
    client_id: <client_id>
    client_secret: <client_secret>

sync:
  interval_minutes: 15
  full_sync_on_first_run: true

database:
  path: ./data/metrics.db

server:
  port: 8080

thresholds:
  stale_ticket_days: 3
  sla_warning_minutes: 30       # Flag tickets within this many minutes of SLA breach
  max_tickets_per_tech: 20
  utilization_target_min: 60
  utilization_target_max: 85
```

### Key Rules for PSA Abstraction

1. **Nothing outside the provider classes should know what PSA we're on.** No SuperOps-specific field names, query syntax, or URL patterns in the sync engine, metrics calculations, API routes, or frontend.
2. **The SQLite schema is PSA-agnostic.** Column names match the normalized data models.
3. **The frontend never calls the PSA API directly.** It talks to the backend REST API only.
4. **Provider selection is a config value.** Switching PSAs: write new provider class, update `psa.provider`, restart. No other changes.
5. **The SuperOpsProvider class is built from scratch** using the proven query patterns documented in the "Proven SuperOps API Reference" section.

---

## Proven SuperOps API Reference

Reference for the SuperOpsProvider class only. The rest of the app should not care about these details. These queries and field names are proven working against a live SuperOps instance.

### Connection Details
- **API URL:** `https://api.superops.ai/msp` (GraphQL)
- **Subdomain:** `<your-subdomain>`
- **Ticket URL template:** `https://helpdesk.<your-domain>.com/#/tickets/{ticket_id}/ticket`
- **Full API docs (MSP):** https://developer.superops.com/msp
- **Full API docs (IT):** https://developer.superops.com/it
- **Timeout:** 30 seconds recommended
- **Page size:** 100

### Auth Headers (proven)
```python
headers = {
    'Authorization': f'Bearer {api_token}',
    'Content-Type': 'application/json',
    'CustomerSubDomain': subdomain,
}
```

### Proven GraphQL Queries

**getTicketList** (proven, primary query):
```graphql
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
```
Note: `source`, `impact`, `urgency`, `category`, `subcategory`, and `worklogTimespent` are confirmed in the API docs but were not used by the internal project. `worklogTimespent` returns a string like `"100.00"` (unit unconfirmed, likely minutes). This field eliminates the need for per-ticket `getWorklogEntries` calls for basic time tracking.

**Pagination variables pattern:**
```python
variables = {
    "input": {
        "page": page,
        "pageSize": 100,
        "condition": {
            "attribute": "status",
            "operator": "notIncludes",
            "value": closed_statuses,
        },
        "sort": [{"attribute": "updatedTime", "order": "DESC"}]
    }
}
```

**getTechnicianList** (proven):
```graphql
query getTechnicianList($input: ListInfoInput!) {
    getTechnicianList(input: $input) {
        userList {
            userId
            name
        }
        listInfo { page pageSize hasMore totalCount }
    }
}
```

**getTicketConversationList** (proven):
```graphql
query getTicketConversationList($input: TicketIdentifierInput!) {
    getTicketConversationList(input: $input) {
        type
    }
}
```
Note: Returns array of conversations. Only confirmed `type` value is `REQ_REPLY` (requester/customer reply). Other values (tech replies, notes, forwards) are undocumented. On first sync, log all unique `type` values to discover the full enum. Check last element to determine who replied last.

**getTicketConversationList (extended, for full conversation data):**
```graphql
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
```
Note: The extended fields (`conversationId`, `content`, `time`, `user`) are documented in the API but not yet tested. Useful for richer conversation tracking and FCR validation.

### Confirmed but Untested Queries (exist in MSP API docs, not yet tested against our instance)

All of these endpoints are confirmed to exist in the SuperOps MSP API documentation. They have NOT been tested against a live instance yet.

**getClientList** (confirmed, low risk):
```graphql
query getClientList($input: ListInfoInput!) {
    getClientList(input: $input) {
        clients {
            accountId
            name
            stage
            status
            emailDomains
            accountManager { userId name }
            primaryContact { userId name }
            hqSite { id name }
            technicianGroups { groupId name }
        }
        listInfo { page pageSize hasMore totalCount }
    }
}
```

**getClientContractList** (confirmed, medium risk - contract type field names undocumented):
```graphql
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
```
Risk: The nested `contract` object's fields (especially contract type) are not documented. `contractStatus` shows `"DRAFT"` but other values are unknown. On first call, log full response to discover the schema.

**getCategoryList** (confirmed, low risk):
Returns `id`, `name`, `subCategories` array.

**getSLAList** (confirmed, low risk):
Returns `id`, `name`.

**getWorklogEntries** (confirmed, high risk - input/output fields undocumented):
Input type `GetWorklogEntriesInput!` exists but filter fields are not documented. Output fields are not fully specified. May not be needed for Phase 1 since `worklogTimespent` on tickets provides total time per ticket.

**getInvoiceList / getInvoice** (confirmed, Phase 2+):
Full invoice data available including `invoiceId`, `displayId`, `client`, `invoiceDate`, `dueDate`, `statusEnum`, `items`, `totalAmount`. Could enable invoice-based billing validation in future phases.

### Important: MSP API vs IT API
The SuperOps MSP API (`developer.superops.com/msp`) and IT API (`developer.superops.com/it`) are **different products with different endpoints**. Client, contract, and worklog endpoints only exist on the MSP API. Always use the MSP API URL: `https://api.superops.ai/msp`.

### Proven Field Mappings
```
technician.userId  -> technician_id (string)
technician.name    -> technician_name
requester.name     -> requester_name (default: 'Unknown')
client.name        -> client_name
techGroup.groupId  -> tech_group_id (string)
techGroup.name     -> tech_group_name
sla.name           -> sla_name
```

### Known Status Values
- Open statuses: "Open", "Customer Replied", "Under Investigation", "On Hold", "Waiting on Customer", "Waiting on third party", "Waiting on Order", "Scheduled"
- Closed statuses: "Resolved", "Closed"

### Known Priority Values (with numeric weights)
```
Very Low: 0
Low: 1
Medium: 2
High: 3
Critical: 4
Urgent: 4
```

### Tech Group IDs
```
<group_id_1>  -> Project Team
<group_id_2>  -> Admin Team
<group_id_3>  -> Sales Team
<group_id_4>  -> Tier 2 Support
<group_id_5>  -> Tier 1 Support
<group_id_6>  -> Pro Services
<group_id_7>  -> CJIS Team
```

### Business Hours
- 8:00 AM to 5:00 PM, America/Los_Angeles timezone

### API Quirks and Workarounds
- **Pagination safety:** Cap at 50 pages for active tickets, 100 pages for historical queries to prevent runaway loops
- **Conversation fetching is slow:** Use concurrent requests (ThreadPoolExecutor) when checking multiple tickets for requester replies
- **Date format:** Strings like `"2022-06-28T05:25:10"` (parse to Python datetime)
- **Date placeholders for filtering:** `placeholder.today`, `placeholder.this.week`, `placeholder.this.month`, etc.
- **Filtering syntax:** `condition` field with AND/OR `joinOperator` and `operands` array
- **Contract types in SuperOps:** Recurring contracts have types like "Service Bundle", "Block Hour", "Block Money". Map these to normalized types.

---

## Tech Stack

- **Backend:** Python (FastAPI preferred, Flask acceptable)
- **Frontend:** React with Tailwind CSS, dark mode by default
- **Database:** SQLite for local caching/historical data (store in `/data` directory)
- **Charts:** Recharts or Chart.js
- **Deployment:** Local, runs with `pip install` + `python main.py` or similar simple startup
- **OS:** Will run on either Windows or Linux (use `pathlib` for all file paths, no hardcoded slashes)

---

## Architecture

### Data Flow

1. **Scheduled sync job** runs every 15 minutes (configurable) calling the PSA provider interface
2. Provider translates PSA-specific data into normalized models
3. Normalized data stored in SQLite
4. Post-sync hooks run: billing flag generation, contract-based billing type sync, stale/reopened ticket detection
5. Frontend requests aggregated metrics from the backend REST API
6. Backend computes metrics by querying SQLite (no live PSA calls for page loads)
7. "Sync Now" button triggers an immediate sync cycle

### Database Schema (SQLite, PSA-Agnostic)

**tickets**
- id (PK, text), display_id, subject, ticket_type, source
- client_id, client_name, site_id, site_name
- requester_id, requester_name
- tech_group_id, tech_group_name
- technician_id, technician_name
- status, priority, impact, urgency
- category, subcategory
- sla_id, sla_name
- created_time, updated_time
- first_response_due, first_response_time, first_response_violated (boolean)
- resolution_due, resolution_time, resolution_violated (boolean)
- worklog_minutes (integer)
- conversation_count (integer; total conversations, for FCR)
- tech_reply_count (integer; outbound tech replies only, for FCR)
- last_conversation_time (datetime; for stale detection)
- last_responder_type (text; "tech" or "requester"; for awaiting-tech-reply detection)
- reopened (boolean, default false; true if ticket was resolved then status reverted to open/in-progress)
- synced_at (timestamp)

**technicians**
- id (PK, text), first_name, last_name, email, role
- available_hours_per_week (decimal, default 40; configurable for utilization calc)

**clients**
- id (PK, text), name

**client_contracts** (synced from PSA)
- contract_id (PK, text)
- client_id (FK to clients.id)
- client_name (denormalized)
- contract_type (text; normalized: "hourly", "block_hour", "block_money", "managed", "per_device", "flat_rate", "other")
- contract_name (text, nullable)
- status (text; "active", "draft", "expired")
- start_date, end_date (date, nullable)
- synced_at (timestamp)

**billing_config** (per-client billing overrides and settings)
- client_id (PK, FK to clients.id)
- billing_type (text; "hourly", "block_hour", "managed", "other"; auto-populated from contract sync, manually overridable)
- hourly_rate (decimal, nullable)
- minimum_bill_minutes (integer, default 15)
- track_billing (boolean, default true; set false to exclude a client from billing audit even if contract says hourly)
- notes (text, nullable)
- auto_detected (boolean; true if billing_type was set from contract sync, false if manually overridden)
- updated_at (timestamp)

**billing_flags** (auto-generated + manual)
- id (PK, auto-increment)
- ticket_id (FK to tickets.id)
- flag_type (enum: MISSING_WORKLOG, ZERO_TIME, LOW_TIME, MANUAL)
- flag_reason (text)
- flagged_at (timestamp)
- resolved (boolean, default false)
- resolved_by (text, nullable)
- resolved_at (timestamp, nullable)
- resolution_note (text, nullable)

**sync_log**
- id, started_at, completed_at, tickets_synced, errors, provider_name

**dashboard_config** (key-value store for settings)
- key (PK, text)
- value (text)
- Examples: "stale_ticket_threshold_days" = "3", "sla_warning_minutes" = "30", "cost_per_month_service_desk" = "25000"

---

## Dashboard Views

### 1. Manage to Zero (Daily Action View)

The "what's broken right now" view. Small set of numbers that should all be zero. The team drives these down by end of day. Could go on the office TV.

**Zero-target cards (big numbers; green = 0, yellow = 1-2, red = 3+):**
- **Unassigned tickets:** Open tickets with no technician assigned
- **No first response:** Tickets with no reply to the customer yet (first_response_time is null)
- **Awaiting tech reply:** Customer replied, tech hasn't responded (last_responder_type = "requester")
- **Stale tickets:** Open tickets with no update in X days (configurable, default 3)
- **SLA breaching soon:** Open tickets where first_response_due or resolution_due is within the configured warning window (default 30 minutes). This is the "about to blow" alarm.
- **SLA already violated:** Open tickets where first_response_violated or resolution_violated is true and the ticket is still open (not yet resolved). These are already late.
- **Unresolved billing flags:** Unbilled/underbilled hourly client tickets

Clicking any card drills into the specific tickets. Every drill-down table is **sorted by priority (highest first) by default**, then by SLA due time (soonest first). Columns: display ID (linked to PSA), subject, client, assigned tech (or "Unassigned"), priority, age, SLA time remaining (or "VIOLATED" in red), last update.

### 2. Work Queue (What to Work On Next)

This is the "stop thinking, start working" view. A single prioritized list of all open tickets, ranked by what should be picked up next. This is not a reporting view; it's an operational tool.

**Ranking logic (configurable weights, but the default sort should be):**
1. **SLA status:** Violated tickets first (already late, fix it now), then tickets closest to breach, then tickets with plenty of time
2. **Priority:** Within the same SLA urgency tier, higher priority tickets rank higher
3. **Age:** Within the same priority, older tickets rank higher (FIFO)

**Display as a single table:**
- Rank (#1, #2, #3, etc.)
- Display ID (linked to PSA)
- Subject
- Client
- Assigned tech (or "Unassigned" in red)
- Priority (color-coded)
- Status
- Age (time since created, human-readable: "2h 15m", "3d 4h")
- **SLA countdown** (time remaining until first response or resolution breach, whichever is sooner. Show as countdown: "1h 22m left" in yellow, "12m left" in red, "VIOLATED 2h ago" in bright red. If no SLA assigned, show "No SLA".)
- Last update
- Worklog time logged

**Filters:**
- Technician (filter to "my tickets" or a specific tech's queue)
- Priority (show only High+ for example)
- Client
- Status
- Unassigned only (toggle)

This view should be fast and feel like a real-time queue. Default: show all open tickets, sorted by the ranking logic above.

### 3. Overview / Home (KPI Dashboard)

KPI cards:
- Total open tickets
- Tickets created today / this week / this month / this year
- Average first response time (this month)
- Average resolution time (this month)
- SLA compliance rate (% with no first response or resolution violations, this month)
- First contact resolution rate (% resolved with only 1 tech reply, this month)
- Total worklog hours (this month)
- Unbilled ticket alerts (unresolved billing flags, red if > 0)
- Open vs. Closed ratio (opened this week vs. closed this week; green if closed >= opened)
- Reopened tickets (count this month; indicates incomplete fixes)

Below KPIs:
- **Ticket volume trend:** Tickets created per day, last 30 days (toggle weekly/monthly)
- **Backlog trend:** Tickets opened vs. closed per week (12 weeks), plus cumulative net backlog line. Net trending up = falling behind.
- **Ticket aging buckets:** Stacked bar or horizontal bar showing open tickets by age: 0-1 day, 1-3 days, 3-7 days, 7-14 days, 14+ days. Shows the shape of the backlog, not just the size.
- **Tickets by status:** Donut/pie of open ticket statuses
- **Tickets by priority:** Horizontal bar of open tickets by priority
- **Workload balance:** Simple bar chart showing open tickets assigned per technician. With 4 techs, imbalance is instantly visible.

### 4. Technician Performance View

Table of all 4 active techs:
- Name
- Open tickets assigned
- Tickets closed (this week / this month, toggle)
- Average first response time
- Average resolution time
- First contact resolution rate
- First response SLA violations (count and %)
- Resolution SLA violations (count and %)
- Total worklog hours
- **Utilization rate** (worklog hours / available hours. Color: green 60-80%, yellow 80-90% or <40%, red >90%)
- Stale tickets count
- Reopened tickets (count of their resolved tickets that got reopened, this month)
- Billing compliance (% of their hourly-client tickets with worklog time)

Clicking a technician drills into:
- Ticket volume over time (chart)
- Breakdown by category
- Breakdown by client
- Current open tickets with age, priority, and SLA time remaining (sorted by priority then SLA)
- SLA-violated tickets
- Stale tickets list
- Reopened tickets list

### 5. Client Drill-Down View

Searchable/filterable table:
- Client name
- **Billing type** (auto-detected from contract sync: hourly, block hour, managed, etc. With manual override indicator)
- Total tickets (all time, this month, this week)
- Open tickets now
- Average resolution time
- SLA compliance rate
- Top categories
- Unresolved billing flags (for billable clients)

Client detail view:
- Ticket volume trend
- Tickets by category (chart)
- Tickets by technician
- Tickets by priority
- **Repeat issue detection:** Category/subcategory combos with 3+ tickets in last 30 days
- **Contract info:** Active contracts for this client (type, status, dates) pulled from client_contracts table
- Full ticket list (sortable by priority by default, filterable)

### 6. SLA Performance View

- Overall SLA compliance (first response and resolution, separately)
- SLA compliance trend (line chart, 90 days)
- **Currently violated:** Table of all open tickets with active SLA violations right now (already late, still open). Sorted by how far past due. This is the "damage report."
- **Close to breach:** Table of open tickets within the warning window. Sorted by time remaining.
- Breakdown by client
- Breakdown by technician
- Breakdown by priority
- Historical violated tickets table (closed tickets that had violations)

### 7. Category Breakdown View

- Tickets by category (bar chart)
- Subcategory breakdown
- Category trends over time
- Average resolution time per category
- Technician-to-category mapping
- **Repeat ticket clusters:** Category/subcategory + client combos with high counts in rolling 30-day windows

### 8. Volume Analytics View

- Daily/weekly/monthly/yearly comparisons with prior periods and averages
- Busiest day of week (bar chart)
- Busiest time of day (bar chart)
- Source breakdown (email, portal, phone, etc.)
- Open vs. Closed weekly comparison (longer history than overview)

### 9. Billing Audit View

Catches revenue leaks from billable clients with missing time entries.

**How billing type detection works:**
- During sync, the system pulls client contracts from the PSA via `get_all_contracts()`
- Contracts are stored in the `client_contracts` table
- For each client with an active contract of type "hourly" or "block_hour", a `billing_config` entry is auto-created (or updated) with `auto_detected = true`
- the helpdesk lead can manually override any client's billing config (e.g. mark a "managed" client as needing time tracking, or exclude a technically-hourly client from auditing)
- Manual overrides set `auto_detected = false` so future contract syncs don't overwrite them

**Auto-flagging rules (each sync, for clients where billing_config.track_billing = true):**
1. **MISSING_WORKLOG:** Resolved/Closed, worklog_minutes is 0 or null
2. **ZERO_TIME:** Worklog entries exist but sum to 0
3. **LOW_TIME:** Resolved/Closed and worklog_minutes < minimum_bill_minutes

**KPI cards:** Unresolved flags (big, red if > 0), estimated unbilled revenue, flags resolved this week/month, % of billable client tickets properly billed

**Flagged tickets table:** Flag type badge, display ID (PSA link), subject, client, tech, status, dates, worklog time, "Mark Resolved" with required note. **Default sort: priority, then date.**

**Filters:** Flag status (Unresolved default), flag type, client, tech, date range

**Billable clients summary:** Client name, billing type, rate, total tickets this month, tickets with time logged, tickets missing time (red %), billed hours, unresolved flags

**Trend chart:** Flag volume over 90 days by type

**Billing config management:**
- Table of all clients with billing config (auto-detected and manual)
- Auto-detected entries show a badge: "From contract" vs. "Manual"
- Edit: override billing type, rate, minimum bill, notes
- Toggle: "Track billing" on/off per client
- New clients with billable contracts are auto-added on next sync

**PSA deep link:** Every ticket display ID links to the PSA via provider's `get_ticket_url()`.

### 10. QBR / Client Report View (Phase 2)

Per-client report generator for Quarterly Business Reviews and reporting to the CEO and Ops Manager.

Select client + date range, generate:
- Ticket volume (opened, closed, currently open)
- SLA compliance (first response and resolution)
- Response and resolution times (averages)
- Top 5 categories with counts
- Technician breakdown
- Worklog hours summary
- Repeat issue highlights
- Reopened ticket count
- Trend comparison vs. previous period
- Contract info summary

Output as printable HTML or PDF export.

---

## Global Controls

- **Date range picker** on every view (Today, This Week, This Month, This Quarter, This Year, Last 30/90 Days, Custom)
- **Client filter** dropdown
- **Technician filter** dropdown
- **Category filter** dropdown
- **Priority filter** dropdown (and priority is the default sort on all ticket tables)
- **Status filter** multi-select
- **Export** CSV for visible table/data
- **Last synced** indicator in header with "Sync Now" button

---

## UX Requirements

- Dark mode by default
- Fast and scannable for the helpdesk lead; presentable in a meeting for the CEO and Ops Manager
- Desktop-optimized, tablet-acceptable
- Loading states, no blank screens
- No auth needed; internal network only
- Brand accents (black #000000, tan/gold #B49B7F), standard dark theme for readability
- PSA name in footer/header (e.g. "Data source: SuperOps") pulled from provider
- **Every ticket table is sortable by clicking column headers. Default sort on all actionable views (Manage to Zero, Work Queue, Billing Audit drill-downs) is priority first, then SLA time remaining.**
- SLA countdown displays: green (>2 hours remaining), yellow (30min-2hr), red (<30min), bright red pulsing ("VIOLATED X ago")

---

## Phase 1 (MVP, single build session)

1. **PSA abstraction layer** with PSAProvider interface and SuperOpsProvider (built from scratch using proven API reference above)
2. **MockProvider** for testing without live PSA
3. **Sync engine** with SQLite storage and post-sync hooks (reopened ticket detection, conversation sync for awaiting-tech-reply)
4. **Manage to Zero** view (unassigned, no response, awaiting tech, stale, SLA breaching, SLA violated, unbilled)
5. **Work Queue** view (prioritized ticket list with SLA countdown)
6. **Overview / Home** with KPI cards and basic charts (volume trend, backlog trend, aging buckets, workload balance)
7. **Technician Performance** view (table with key metrics, drill-down with open tickets)
8. **Billing Audit** view (basic: flag tickets from billable clients with zero worklogTimespent; uses ticket-level field, no getWorklogEntries dependency)
9. Global filters (date range, client, technician, priority)
10. Sync Now button, last-synced indicator
11. **First-run API discovery:** On first sync, log raw responses from getClientList, getClientContractList, and getTicketConversationList to discover undocumented field values (contract types, conversation type enum, worklogTimespent unit). Output to console and sync_log.

## Phase 2

1. **Billing Audit enhancements** (contract-based auto-detection via getClientContractList, per-ticket worklog detail via getWorklogEntries if needed, billing config management UI)
2. **Client Drill-Down** view with repeat issue detection and contract info
3. **SLA Performance** view (currently violated, close to breach, historical)
4. **Category Breakdown** view with repeat ticket clusters
5. **Volume Analytics** view
6. **QBR / Client Report** generator (printable per-client summary)
7. CSV export on all tables
8. Historical trend comparisons (month-over-month, year-over-year)
9. Cost per ticket tracking (configurable monthly cost / tickets closed)
10. Escalation rate tracking (detect technician reassignments)
11. Scheduled email reports (weekly summary to the CEO and Ops Manager)

## Phase 3 (Future)

1. **HaloPSA provider** implementation
2. CSAT integration if we add satisfaction surveys

---

## Notes for Claude Code

- **This is a brand new application.** Do not look for or reference any existing codebase. Build from scratch.
- **The PSA abstraction layer is not optional.** Every PSA interaction goes through the provider interface. No SuperOps-specific code outside the provider. No exceptions.
- **Sync failure handling:** If a sync fails partway through, do not leave partial data. Use SQLite transactions; commit only after a full sync cycle completes successfully. The dashboard should continue serving the last good data during a failed sync, and log the error to sync_log.
- Never use em dashes in any output, code comments, or UI text. Use commas, periods, semicolons, or parentheses instead.
- Use `pathlib` for all file paths. This app must run on both Windows and Linux.
- Paginate through ALL results when syncing. Provider handles pagination internally.
- Handle API rate limits with retries and backoff inside the provider.
- Parse all dates to Python datetime objects in the provider. The app never sees raw PSA date strings.
- `worklog_minutes` stored as integer minutes. Source: `worklogTimespent` field on each ticket (string like "100.00"). Parse to float, assume minutes (validate on first sync by comparing a known ticket). Display as "Xh Ym" in UI. This avoids per-ticket getWorklogEntries calls entirely.
- Full initial sync on first run, then incremental syncs via updated_time filters.
- **First-run discovery mode:** On the very first sync, log full raw API responses from getClientList (1 page), getClientContractList (1 page), and a sample getTicketConversationList to the console. This lets us discover undocumented field names, contract type values, conversation type enum values, and confirm worklogTimespent units without guessing.
- API endpoints: `/api/sync`, `/api/health`, `/api/billing/*`, `/api/config`, `/api/work-queue`.
- Log syncs to console and sync_log table, including `provider_name`.
- **Billing detection:** On each sync, pull contracts via `get_all_contracts()`. For clients with active hourly/block_hour contracts, auto-create or update `billing_config` entries with `auto_detected = true`. Never overwrite entries where `auto_detected = false` (manual overrides).
- **Billing flags** run as post-sync hook. No duplicate flags. Auto-resolve if worklog time appears.
- **Stale ticket detection** is a query against `last_conversation_time`/`updated_time`, not stored state.
- **SLA countdown** is calculated at query time: `first_response_due - now()` or `resolution_due - now()`, whichever is sooner and still relevant. The database stores the due times; the countdown is computed live.
- **Reopened detection:** During sync, if a ticket has `resolution_time` set but its status is not Resolved/Closed, mark `reopened = true`. This catches tickets that were resolved and then re-opened.
- **FCR:** Ticket is "first contact resolved" if resolved/closed with tech_reply_count = 1 and was resolved within 4 hours of creation (to filter out tickets that sat open with no real interaction). Consider syncing conversation counts only for recently closed tickets to avoid expensive bulk conversation fetches.
- **Utilization:** (worklog_minutes in period) / (available_hours_per_week * weeks * 60). Configurable per tech.
- **Awaiting tech reply:** Store `last_responder_type` ("tech" or "requester") during conversation sync. SuperOps `getTicketConversationList` returns a `type` field. Only `REQ_REPLY` is documented; other values (tech replies, notes) are unknown. On first sync, log all unique `type` values to build the mapping. Treat `REQ_REPLY` as "requester", everything else as "tech" until we discover the full enum.
- **Work Queue ranking:** Compute a numeric score for each open ticket: SLA urgency (violated = 1000, <30min = 500, <2hr = 200, etc.) + priority weight (Critical = 100, High = 75, Medium = 50, Low = 25) + age bonus (1 point per hour old). Sort descending. These weights are defaults; make them configurable via dashboard_config so the helpdesk lead can tune them without code changes.
- **Priority is the default sort** on every ticket table in every actionable view. Column headers are clickable to re-sort.
- **Include a MockProvider** that returns static test data for frontend development and testing without a live PSA connection.
