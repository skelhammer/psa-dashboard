# PSA Dashboard

## Project Rules
- PSA abstraction is mandatory. No SuperOps-specific code outside `backend/app/psa/superops.py`.
- Phone provider abstraction is mandatory. No Zoom-specific code outside `backend/app/phone/zoom.py`.
- Never use em dashes in code, comments, or UI text. Use commas, periods, semicolons, or parentheses.
- Use `pathlib` for all file paths (cross-platform: Windows and Linux).
- SQLite schema is PSA-agnostic. Column names match normalized data models.
- Frontend never calls PSA or phone APIs directly; it talks to backend REST API only.
- Priority is the default sort on every ticket table.
- Dark mode by default (true black #09090B / zinc). Brand primary: blue #3B82F6.

## Tech Stack
- Backend: Python FastAPI + SQLite (aiosqlite) + APScheduler
- Frontend: React 19 + TypeScript + Tailwind CSS + Recharts + TanStack Query + Lucide React
- Config: YAML (config.yaml, gitignored; config.example.yaml checked in)

## Key Modules
- `backend/app/psa/` - PSA provider abstraction (base, superops, mock)
- `backend/app/phone/` - Phone provider abstraction (base, zoom, mock)
- `backend/app/alerts/` - Alert engine for threshold-based notifications
- `backend/app/sync/` - Sync engine, post-sync hooks, phone sync, scheduler
- `backend/app/api/` - FastAPI routes (overview, queue, billing, clients, technicians, executive, phone, alerts, mtz, sync, filters)
- `frontend/src/pages/` - Overview, WorkQueue, Technicians, ClientHealth, BillingAudit, ManageToZero, PhoneAnalytics, ExecutiveReport

## Running
1. Copy `config.example.yaml` to `config.yaml` and fill in secrets (or leave as `mock` provider for testing).
2. Backend:
   ```
   cd backend
   python -m venv .venv
   source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python run.py
   ```
3. Frontend (separate terminal):
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:3000 (frontend dev server proxies API to backend on :8080).
