# PSA Dashboard

## Project Rules
- PSA abstraction is mandatory. No SuperOps-specific code outside `backend/app/psa/superops.py`. No Zendesk-specific code outside `backend/app/psa/zendesk.py`.
- Phone provider abstraction is mandatory. No Zoom-specific code outside `backend/app/phone/zoom.py`.
- Never use em dashes in code, comments, or UI text. Use commas, periods, semicolons, or parentheses.
- Use `pathlib` for all file paths (cross-platform: Windows and Linux).
- SQLite schema is PSA-agnostic. Column names match normalized data models.
- Frontend never calls PSA or phone APIs directly; it talks to backend REST API only.
- Priority is the default sort on every ticket table.
- Dark mode by default (true black #09090B / zinc). Brand primary: blue #3B82F6.
- Multiple PSA providers can run simultaneously. Each provider's data is isolated via ID prefixing (e.g. superops:123, zendesk:456) and a `provider` column.
- Technicians can be merged across providers via `tech_merge_map` in config (Zendesk tech ID -> SuperOps prefixed ID).
- Corp tickets (Zendesk custom field) are tagged with `is_corp` and toggleable in the UI; not excluded at the API level.
- Credentials (API tokens, subdomains, usernames, OAuth secrets) live in the encrypted vault (`vault_secrets` table in `backend/data/metrics.db`) and are managed through the Settings page in the dashboard. Never put credentials in `config.yaml`. Code that constructs providers must pull credentials from `SecretsManager` via `psa/factory.py` or `phone/factory.py`, never read them directly from yaml. New credential fields go in `backend/app/vault/keys.py` so the migration, factories, and Settings UI all see them automatically.
- Routes under `/api/admin/*` and `POST /api/auth/password` MUST use the `require_admin` dependency from `app.auth.middleware`. Read endpoints (`/api/overview`, etc.) remain unauthenticated.

## Tech Stack
- Backend: Python FastAPI + SQLite (aiosqlite) + APScheduler + cryptography (AES-256-GCM) + bcrypt + itsdangerous
- Frontend: React 19 + TypeScript + Tailwind CSS + Recharts + TanStack Query + Lucide React
- Config: YAML (config.yaml, gitignored; config.example.yaml checked in) for non-secret settings only. Credentials live in the encrypted vault.

## Key Modules
- `backend/app/psa/` - PSA provider abstraction (base, superops, zendesk, mock, factory). Factory is async and pulls credentials from the vault.
- `backend/app/phone/` - Phone provider abstraction (base, zoom, mock, factory). Same async + vault pattern.
- `backend/app/vault/` - Encrypted secrets storage. `crypto.py` (AES-256-GCM with KEK/DEK), `manager.py` (SecretsManager), `keys.py` (canonical SECRET_KEYS registry mapping vault keys to yaml paths), `migrate.py` (one-time plaintext-yaml-to-vault migration with auto-redaction), `audit.py` (mutation audit log), `cli.py` (advanced: generate-kek, rotate-kek, set-admin-password).
- `backend/app/auth/` - Admin authentication. `passwords.py` (bcrypt + constant-time verify), `session.py` (signing key bootstrap), `users.py` (single-user admin row), `ratelimit.py` (sliding window login limiter), `middleware.py` (`require_admin` dependency).
- `backend/app/lifecycle/providers.py` - Hot reload: `rebuild_for_key(app, key)` swaps the affected provider into `app.state.manager.engines` (or restarts the phone task) when a credential changes, no backend restart required.
- `backend/app/alerts/` - Alert engine for threshold-based notifications.
- `backend/app/sync/` - Sync engine, post-sync hooks, phone sync, scheduler, multi-provider manager.
- `backend/app/api/` - FastAPI routes (overview, queue, billing, clients, technicians, executive, phone, alerts, mtz, sync, filters, contracts, auth, admin_secrets). The auth and admin_secrets routers are added in `main.py` `create_app()` along with `SessionMiddleware`.
- `backend/tests/` - Pytest suite covering vault crypto, secrets manager, yaml migration, lifespan wiring, password hashing, login rate limiter, and admin routes (89 tests).
- `frontend/src/pages/` - Overview, WorkQueue, Technicians, TechnicianDetail, ClientHealth, ClientDetail, BillingAudit, ManageToZero, PhoneAnalytics, ExecutiveReport, Contracts, Settings.
- `frontend/src/api/admin.ts` - Typed API client and TanStack Query hooks for the auth + admin secrets endpoints.
- `deploy/SECRETS-DEPLOYMENT.md` - Live-server migration runbook for the encrypted credentials vault.

## Running
1. Copy `config.example.yaml` to `config.yaml`. The example contains only non-secret settings (timezone, intervals, business hours, billing rules, Zendesk display overrides). Credentials go through the Settings UI on first launch. Leave `psa.providers: [mock]` if you want to run without any real credentials.
2. Backend:
   ```
   cd backend
   python -m venv .venv
   source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python run.py
   ```
   On first run, the backend auto-generates `backend/data/.vault_master_key` and `backend/data/.session_signing_key`. Both are gitignored. Back up the master key to a password manager (it decrypts your stored credentials).
3. Frontend (separate terminal):
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:3000 (frontend dev server proxies API to backend on :8880).
5. Click **Settings** in the sidebar. On first visit you will be prompted to set the admin password, then enter API tokens / subdomains / usernames for each provider you enabled in step 1.

## Testing
```
cd backend
.venv/Scripts/activate    # Windows: .venv\Scripts\activate
python -m pytest tests/
```
89 tests cover vault crypto, secrets manager, yaml migration, lifespan wiring, password hashing, login rate limiter, and admin routes. Any change to vault crypto, auth logic, or the admin API should pass all of them before shipping. Vault failures are silent and dangerous (a broken AES nonce would still let you save and read secrets in the UI but produce ciphertext an attacker could trivially break), so the test suite is the only line of defense against regressions in that code.

## Deploying credential changes to the live server
See `deploy/SECRETS-DEPLOYMENT.md` for the full runbook. Summary: `sudo bash update.sh` on the live VM. The migration runs automatically on the first restart with new code; the runbook covers verification, rollback, and recovery scenarios for forgotten admin password and lost master key.
