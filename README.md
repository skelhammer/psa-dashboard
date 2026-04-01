# PSA Dashboard

A real-time helpdesk metrics dashboard that syncs with your PSA (Professional Services Automation) platform and provides actionable insights for MSP teams.

## Features

- **Overview:** Clickable KPI cards with contextual navigation, ticket volume trends (auto-granularity per day/week/month), daily new tickets chart, backlog tracking, SLA compliance, workload balance, pie charts with floating labels, and group distribution charts. Multi-section CSV and portrait PDF export.
- **Work Queue:** Scored and ranked open tickets prioritized by SLA urgency, priority, and age
- **Technician Performance:** Sortable table view and leaderboard with gold/silver/bronze trophy rankings. Multiple leaderboard modes (productivity, response time, resolution time, SLA compliance, hours billed). Per-tech detail pages with KPI cards, volume/SLA trend charts, category/client breakdowns, and open ticket lists.
- **Client Health:** Per-client metrics with SLA compliance, ticket volume, and drill-down detail pages with trend charts and category breakdowns
- **Billing Audit:** Flags for billable client tickets missing worklogs, with per-client summaries, profitability metrics, and resolution tracking
- **Manage to Zero:** Zero-target cards for unassigned tickets, SLA violations, stale tickets, and more
- **Phone Analytics:** Call volume, duration, and queue metrics via Zoom Phone integration (or mock data)
- **Executive Report:** CEO summary with high-level KPIs, alerts, and client profitability insights
- **Alerts:** Threshold-based alert engine for SLA breaches, stale tickets, and workload imbalances
- **Global Filters:** Provider toggle (All/SuperOps/Zendesk), Corp ticket toggle, date range presets with custom date pickers, plus client, technician, priority, and tech group filters on every page
- **Auto Sync:** Background sync on a configurable interval with incremental updates, nightly full sync, and automatic cleanup of deleted tickets
- **Export:** Per-page PDF export (portrait, multi-page with headers/footers) and CSV export (multi-section for overview, per-chart for individual charts)

## Supported Providers

### PSA (multiple can run simultaneously)
- **SuperOps:** Full support (tickets, clients, technicians, contracts, conversations)
- **Zendesk:** Full support (tickets, organizations, agents, comments, custom statuses, Corp tagging, extra agents)
- **Mock:** Built-in mock data for testing without API credentials
- Architecture supports adding new providers (HaloPSA stub included)

### Multi-Provider Features
- **Provider toggle:** Frontend segmented button to view All, SuperOps only, or Zendesk only
- **Tech merge:** Map Zendesk technicians to their SuperOps counterparts via `tech_merge_map` so stats unify under one record
- **Corp toggle:** Zendesk tickets tagged with a custom field can be shown/hidden via a toggle switch
- **ID isolation:** Each provider's data is prefixed (superops:123, zendesk:456) to prevent collisions
- **Independent sync:** Each provider syncs on its own schedule; one provider's sync never deletes the other's data

### Phone
- **Zoom Phone:** Call logs, queue stats, user metrics (requires Server-to-Server OAuth app)
- **Mock:** Built-in mock data for testing without API credentials

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLite (aiosqlite), APScheduler
- **Frontend:** React 19, TypeScript, Tailwind CSS, Recharts, TanStack Query, Lucide React
- **Config:** YAML (secrets in gitignored `config.yaml`, template in `config.example.yaml`)

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/skelhammer/psa-dashboard.git
cd psa-dashboard
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your settings:

```yaml
psa:
  providers: [superops, zendesk]  # or [mock] for testing
  superops:
    api_url: https://api.superops.ai/msp
    api_token: YOUR_API_TOKEN
    subdomain: YOUR_SUBDOMAIN
  zendesk:
    subdomain: YOUR_SUBDOMAIN
    email: agent@yourcompany.com
    api_token: YOUR_ZENDESK_API_TOKEN
    page_size: 100
    ticket_url_template: "https://yourcompany.zendesk.com/agent/tickets/{ticket_id}"

phone:
  provider: zoom  # or "mock" or "none"
  zoom:
    account_id: YOUR_ZOOM_ACCOUNT_ID
    client_id: YOUR_ZOOM_CLIENT_ID
    client_secret: YOUR_ZOOM_CLIENT_SECRET

server:
  timezone: America/Los_Angeles  # Your IANA timezone

billing:
  unlimited_plans: ["Managed Plan A"]  # Contract names excluded from billing audit
  tech_cost_per_hour: 55             # For profitability calculations
```

### 3. Install and run

#### Quick start (recommended)

The included launch scripts handle venv creation, dependency installation, and starting both servers.

**Windows:**

Double-click `start.bat`, or from a terminal:

```powershell
start.bat
```

**Linux / macOS:**

```bash
./start.sh
```

#### Manual setup

If you prefer to run the backend and frontend separately:

**Windows** (two terminals):

```powershell
# Terminal 1 - Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

```powershell
# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

**Linux / macOS** (two terminals):

```bash
# Terminal 1 - Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

```bash
# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

#### Production install (Ubuntu)

The included `install.sh` script sets up the dashboard as a systemd service behind nginx. It handles all dependencies, builds the frontend, and configures everything to start on boot.

```bash
sudo bash install.sh
```

This will:
- Install Python 3, Node.js 22, and nginx
- Set up the Python venv and install dependencies
- Build the frontend for production
- Create a `psa-dashboard` systemd service for the backend
- Configure nginx to serve the frontend and proxy API requests

After install, open **http://your-server-ip:5051** in your browser.

**Managing the service:**

```bash
sudo systemctl status psa-dashboard    # check status
sudo systemctl restart psa-dashboard   # restart after config changes
sudo systemctl stop psa-dashboard      # stop the backend
journalctl -u psa-dashboard -f         # tail logs
```

**Configuration** lives at `config.yaml` in the repo directory. Edit it and restart the service to apply changes:

```bash
nano config.yaml
sudo systemctl restart psa-dashboard
```

**Updating** after pulling new code: re-run `sudo bash install.sh`. Your `config.yaml` is preserved across runs.

### 4. Open the dashboard

**Development:** Go to **http://localhost:3000**. The frontend dev server proxies API requests to the backend on port 8880.

**Production (Ubuntu):** Go to **http://your-server-ip:5051** (served by nginx).

On first launch, the backend runs a full sync from your PSA provider(s), which may take a couple of minutes depending on ticket volume. Subsequent syncs are incremental and run every 15 minutes by default. A full sync runs automatically at midnight to clean up deleted/trashed tickets.

## Project Structure

```
psa-dashboard/
  install.sh                 # Ubuntu production installer (systemd + nginx)
  start.bat                  # Windows launch script
  start.sh                   # Linux/macOS launch script
  update.sh                  # Pull and rebuild script
  config.example.yaml        # Template config (tracked)
  config.yaml                # Your config with secrets (gitignored)
  backend/
    run.py                   # Entry point
    requirements.txt         # Python dependencies
    app/
      api/                   # FastAPI routes and dependencies
      psa/                   # PSA provider abstraction
        base.py              # Abstract base class
        superops.py          # SuperOps GraphQL implementation
        zendesk.py           # Zendesk REST API v2 implementation
        mock.py              # Mock data provider
        factory.py           # Multi-provider factory
      phone/                 # Phone provider abstraction
        base.py              # Abstract base class
        zoom.py              # Zoom Phone implementation
        mock.py              # Mock data provider
      alerts/                # Threshold-based alert engine
      sync/                  # Sync engine, hooks, phone sync
        engine.py            # Per-provider sync with ID prefixing
        manager.py           # Multi-provider sync coordinator
        scheduler.py         # Background sync scheduler
        hooks.py             # Post-sync hooks (billing flags, conversations)
      config.py              # Settings loader
      database.py            # SQLite schema and migrations
      models.py              # PSA-agnostic data models
    data/
      metrics.db             # SQLite database (auto-created, gitignored)
  frontend/
    src/
      api/                   # API client and React Query hooks
      components/            # Shared UI components
      context/               # Filter state context (provider, corp, dates)
      pages/                 # Page components
      utils/                 # Formatting helpers and constants
```

## Configuration Reference

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `psa.providers` | | `[mock]` | List of active PSA providers: `superops`, `zendesk`, `mock` |
| `psa.superops.api_url` | | `https://api.superops.ai/msp` | SuperOps API URL |
| `psa.superops.api_token` | | | SuperOps API bearer token |
| `psa.superops.subdomain` | | | SuperOps subdomain |
| `psa.zendesk.subdomain` | | | Zendesk subdomain (e.g. `yourcompany`) |
| `psa.zendesk.email` | | | Zendesk agent email for API auth |
| `psa.zendesk.api_token` | | | Zendesk API token |
| `psa.zendesk.page_size` | | `100` | Results per Zendesk API page |
| `psa.zendesk.ticket_url_template` | | | URL template with `{ticket_id}` placeholder |
| `psa.zendesk.exclude_custom_fields` | | `[]` | Custom field rules for Corp tagging (e.g. `["custom_field_123:true"]`) |
| `psa.zendesk.status_display_overrides` | | `{}` | Map custom status labels to display names |
| `psa.zendesk.extra_agents` | | `{}` | Map of Zendesk user IDs to names for agents not returned by search |
| `psa.zendesk.tech_merge_map` | | `{}` | Map Zendesk tech IDs to SuperOps prefixed IDs for unified stats |
| `phone.provider` | | `none` | Phone provider: `zoom`, `mock`, or `none` |
| `phone.zoom.account_id` | | | Zoom Server-to-Server OAuth Account ID |
| `phone.zoom.client_id` | | | Zoom OAuth Client ID |
| `phone.zoom.client_secret` | | | Zoom OAuth Client Secret |
| `sync.interval_minutes` | | `15` | Minutes between PSA background syncs |
| `phone_sync.interval_minutes` | | `5` | Minutes between phone data syncs |
| `phone_sync.lookback_days` | | `30` | Days of phone history to sync |
| `database.path` | | `./data/metrics.db` | SQLite database file path |
| `server.host` | | `0.0.0.0` | Backend listen address |
| `server.port` | | `8880` | Backend listen port |
| `server.timezone` | | `America/Los_Angeles` | IANA timezone for date calculations |
| `server.closed_statuses` | | `["Resolved", "Closed"]` | Ticket statuses considered terminal |
| `billing.unlimited_plans` | | `[]` | Contract names excluded from billing audit |
| `billing.tech_cost_per_hour` | | `55` | Average fully-loaded cost per tech hour |
| `thresholds.stale_ticket_days` | | `3` | Days before an open ticket is considered stale |
| `thresholds.sla_warning_minutes` | | `30` | Minutes before SLA breach to show warning |
| `thresholds.max_tickets_per_tech` | | `20` | Target max open tickets per technician |
| `thresholds.utilization_target_min` | | `60` | Minimum utilization % (green zone) |
| `thresholds.utilization_target_max` | | `85` | Maximum utilization % (green zone) |
| `business_hours.enabled` | | `true` | Enable business hours filtering |
| `business_hours.start_hour` | | `8` | Business day start (24h) |
| `business_hours.end_hour` | | `17` | Business day end (24h) |
| `business_hours.work_days` | | `[1,2,3,4,5]` | Working days (Mon=1 through Fri=5) |
| `business_hours.holidays` | | `[]` | ISO dates to exclude (e.g., `["2026-01-01"]`) |

## Zoom Phone Setup

To use live Zoom Phone data instead of mock data:

1. Go to [marketplace.zoom.us](https://marketplace.zoom.us) and sign in as admin
2. Click **Develop** then **Build App**
3. Select **Server-to-Server OAuth** and create the app
4. Add scopes: `phone:read:admin`, `phone:read:call_log:admin`, `phone:read:call_queue:admin`
5. Fill in required app info and click **Activate**
6. Copy Account ID, Client ID, and Client Secret to `config.yaml`
7. Set `phone.provider: zoom` and restart the backend

Requires a Zoom Business/Enterprise account with an active Zoom Phone license.
