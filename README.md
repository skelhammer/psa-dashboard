# PSA Dashboard

A real-time helpdesk metrics dashboard that syncs with your PSA (Professional Services Automation) platform and provides actionable insights for MSP teams.

## Features

- **Overview** -- KPI cards, ticket volume trends, backlog tracking, SLA compliance, workload balance, and group distribution charts
- **Work Queue** -- Scored and ranked open tickets prioritized by SLA urgency, priority, and age
- **Technician Performance** -- Per-tech metrics including closed tickets, response times, worklog hours, utilization, and billing compliance
- **Billing Audit** -- Flags for billable client tickets missing worklogs, with per-client summaries and resolution tracking
- **Manage to Zero** -- Zero-target cards for unassigned tickets, SLA violations, stale tickets, and more
- **Global Filters** -- Date range presets with custom date pickers, plus client, technician, and priority filters on every page
- **Auto Sync** -- Background sync on a configurable interval with incremental updates

## Supported PSA Providers

- **SuperOps** -- Full support (tickets, clients, technicians, contracts, conversations)
- **Mock** -- Built-in mock data for testing without API credentials
- Architecture supports adding new providers (HaloPSA stub included)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLite (aiosqlite), APScheduler
- **Frontend:** React 18, TypeScript, Tailwind CSS, Recharts, TanStack Query
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
  provider: superops  # or "mock" for testing
  superops:
    api_url: https://api.superops.ai/msp
    api_token: YOUR_API_TOKEN
    subdomain: YOUR_SUBDOMAIN

billing:
  hourly_plans: ["MSP Basic", "MSP Advanced", "Break Fix"]
  unlimited_plans: ["MSP Platinum", "MSP Premium"]

server:
  timezone: America/Los_Angeles  # Your IANA timezone
```

### 3. Install and run

#### Windows

Open two terminals (PowerShell or Command Prompt):

**Terminal 1 (Backend):**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

**Terminal 2 (Frontend):**

```powershell
cd frontend
npm install
npm run dev
```

#### Linux / macOS

Open two terminals:

**Terminal 1 (Backend):**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

**Terminal 2 (Frontend):**

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the dashboard

Go to **http://localhost:3000** in your browser.

The frontend dev server proxies API requests to the backend on port 8080. On first launch, the backend runs a full sync from your PSA provider, which may take a couple of minutes depending on ticket volume. Subsequent syncs are incremental and run every 15 minutes by default.

## Project Structure

```
psa-dashboard/
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
        mock.py              # Mock data provider
      sync/                  # Sync engine and post-sync hooks
      config.py              # Settings loader
      database.py            # SQLite schema
      models.py              # PSA-agnostic data models
    data/
      metrics.db             # SQLite database (auto-created)
  frontend/
    src/
      api/                   # API client and React Query hooks
      components/            # Shared UI components
      context/               # Filter state context
      pages/                 # Page components
      utils/                 # Formatting helpers and constants
```

## Configuration Reference

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `psa.provider` | | `mock` | PSA provider: `superops` or `mock` |
| `sync.interval_minutes` | | `15` | Minutes between background syncs |
| `database.path` | | `./data/metrics.db` | SQLite database file path |
| `server.host` | | `0.0.0.0` | Backend listen address |
| `server.port` | | `8080` | Backend listen port |
| `server.timezone` | | `America/Los_Angeles` | IANA timezone for date calculations |
| `billing.hourly_plans` | | `[]` | Client plan names that indicate hourly billing |
| `billing.unlimited_plans` | | `[]` | Client plan names excluded from billing audit |
| `thresholds.stale_ticket_days` | | `3` | Days before an open ticket is considered stale |
| `thresholds.sla_warning_minutes` | | `30` | Minutes before SLA breach to show warning |
| `thresholds.max_tickets_per_tech` | | `20` | Target max open tickets per technician |
