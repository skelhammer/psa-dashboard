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

Edit `config.yaml` with your **non-secret** settings:

```yaml
psa:
  providers: [superops, zendesk]  # or [mock] for testing
  superops:
    api_url: https://api.superops.ai/msp
  zendesk:
    page_size: 100
    ticket_url_template: "https://yourcompany.zendesk.com/agent/tickets/{ticket_id}"

phone:
  provider: zoom  # or "mock" or "none"

server:
  timezone: America/Los_Angeles  # Your IANA timezone

billing:
  unlimited_plans: ["Managed Plan A"]  # Contract names excluded from billing audit
  tech_cost_per_hour: 55             # For profitability calculations
```

> **Credentials (API tokens, subdomains, Zendesk email, Zoom OAuth) are
> NOT stored in `config.yaml`.** They are managed through the Settings page
> in the dashboard UI on first launch and stored encrypted (AES-256-GCM) in
> the SQLite database. The first time you visit `/settings` you will be
> prompted to set an admin password, then you can enter your API tokens.
> See `deploy/SECRETS-DEPLOYMENT.md` for the full credential management
> workflow including rotation, backup, and recovery.

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

**Configuration:**
- **Credentials** (API tokens, subdomains, Zendesk email, Zoom OAuth) are managed through the Settings page in the dashboard at `http://your-server-ip:5051/settings`. No service restart needed; the backend hot-reloads providers when you save a new value. See `deploy/SECRETS-DEPLOYMENT.md` for backup, rotation, and recovery.
- **Non-secret settings** (timezone, sync intervals, business hours, billing rules, Zendesk display overrides) live in `config.yaml`. Edit and restart to apply:
  ```bash
  nano config.yaml
  sudo systemctl restart psa-dashboard
  ```

**Updating** after pulling new code: `sudo bash update.sh`. Your `config.yaml` and encrypted vault are preserved across updates.

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

> **Credential fields** (marked **UI** below) are managed through the
> Settings page in the dashboard, NOT in `config.yaml`. They are stored
> encrypted in the SQLite database. Listed here for reference only.

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `psa.providers` | | `[mock]` | List of active PSA providers: `superops`, `zendesk`, `mock` |
| `psa.superops.api_url` | | `https://api.superops.ai/msp` | SuperOps API URL |
| `psa.superops.api_token` | | **UI** | SuperOps API bearer token (Settings page) |
| `psa.superops.subdomain` | | **UI** | SuperOps subdomain (Settings page) |
| `psa.zendesk.subdomain` | | **UI** | Zendesk subdomain, e.g. `yourcompany` (Settings page) |
| `psa.zendesk.email` | | **UI** | Zendesk agent email for API auth (Settings page) |
| `psa.zendesk.api_token` | | **UI** | Zendesk API token (Settings page) |
| `psa.zendesk.page_size` | | `100` | Results per Zendesk API page |
| `psa.zendesk.ticket_url_template` | | | URL template with `{ticket_id}` placeholder |
| `psa.zendesk.exclude_custom_fields` | | `[]` | Custom field rules for Corp tagging (e.g. `["custom_field_123:true"]`) |
| `psa.zendesk.status_display_overrides` | | `{}` | Map custom status labels to display names |
| `psa.zendesk.extra_agents` | | `{}` | Map of Zendesk user IDs to names for agents not returned by search |
| `psa.zendesk.tech_merge_map` | | `{}` | Map Zendesk tech IDs to SuperOps prefixed IDs for unified stats |
| `phone.provider` | | `none` | Phone provider: `zoom`, `mock`, or `none` |
| `phone.zoom.account_id` | | **UI** | Zoom Server-to-Server OAuth Account ID (Settings page) |
| `phone.zoom.client_id` | | **UI** | Zoom OAuth Client ID (Settings page) |
| `phone.zoom.client_secret` | | **UI** | Zoom OAuth Client Secret (Settings page) |
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
6. Set `phone.provider: zoom` in `config.yaml` and restart the backend
7. Open the dashboard, go to **Settings**, and paste Account ID, Client ID, and Client Secret into the Zoom Phone fields

Requires a Zoom Business/Enterprise account with an active Zoom Phone license.

## Credential Management

API tokens, subdomains, Zendesk email, and Zoom OAuth credentials are managed through the **Settings** page in the dashboard rather than in `config.yaml`. The first time you visit `/settings` you will be prompted to set an admin password, then you can enter your credentials. Stored values are encrypted with AES-256-GCM in the SQLite database.

- **Set or rotate a credential:** Settings page in the dashboard. The backend hot-reloads the affected provider; no restart needed.
- **Forgot the admin password:** reset it from the server CLI. See `deploy/SECRETS-DEPLOYMENT.md` recovery section.
- **Backup and disaster recovery:** the master key file at `backend/data/.vault_master_key` decrypts the stored credentials. Back it up alongside `metrics.db`. See `deploy/SECRETS-DEPLOYMENT.md`.
- **Migrating an existing install** with plaintext secrets in `config.yaml`: see `deploy/SECRETS-DEPLOYMENT.md`. The migration is automatic on first restart with the new code; the runbook covers verification, rollback, and post-migration cleanup.
