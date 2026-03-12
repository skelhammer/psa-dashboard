# PSA Dashboard

## Project Rules
- PSA abstraction is mandatory. No SuperOps-specific code outside `backend/app/psa/superops.py`.
- Never use em dashes in code, comments, or UI text. Use commas, periods, semicolons, or parentheses.
- Use `pathlib` for all file paths (cross-platform: Windows and Linux).
- SQLite schema is PSA-agnostic. Column names match normalized data models.
- Frontend never calls PSA API directly; it talks to backend REST API only.
- Priority is the default sort on every ticket table.
- Dark mode by default (true black #09090B / zinc). Brand primary: blue #3B82F6.

## Tech Stack
- Backend: Python FastAPI + SQLite (aiosqlite)
- Frontend: React + TypeScript + Tailwind CSS + Recharts + Lucide React
- Config: YAML (config.yaml, gitignored; config.example.yaml checked in)

## Running
1. Copy `config.example.yaml` to `config.yaml` and fill in secrets (or leave as `mock` provider for testing).
2. Backend:
   ```
   cd backend
   python -m venv .venv
   source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
   pip install fastapi uvicorn httpx pyyaml aiosqlite apscheduler
   python run.py
   ```
3. Frontend (separate terminal):
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:3000 (frontend dev server proxies API to backend on :8080).
