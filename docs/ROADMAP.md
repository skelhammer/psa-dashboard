# PSA Dashboard → Internal MSP Ops Cockpit

## Context

The PSA Dashboard today is a clean React 19 + FastAPI + SQLite app that pulls from SuperOps, Zendesk, and Zoom. The owner wants to keep evolving it into the MSP's internal operations cockpit — a read-only aggregation dashboard, not a PSA replacement. SuperOps stays the PSA. Hudu-style docs, CloudRadial-style client portals, Rewst-style automation are explicitly NOT in scope. Deployment is LAN-only with no planned internet exposure.

The work targets five concrete outcomes:

1. Datto RMM integrated (read-only) so we can see device inventory, online/offline, patch status, and alerts per client alongside tickets.
2. A unified client/agent/device identity layer so one company row unifies SuperOps + Zendesk + Zoom + Datto + QBO and the dashboard shows "everything about Acme" on one page.
3. QuickBooks Online integrated (read-only) for invoices, AR aging, payment status, time-activity, and per-client profitability.
4. Four new cross-system aggregation features: expiring-contracts alerts, AR aging + unbilled-time dashboard, incoming-call context panel with leaderboards, and a per-client profitability scorecard.
5. Foundational hardening that matters even on a LAN: off-host backup of `metrics.db` + `.vault_master_key`, a data-correctness fix to provider-scoped post-sync hooks, admin-setup race fix, a CI pipeline, real health checks, and the filter/abstraction refactors that unblock billing + RMM domains.

Devil's-advocate guidance the plan honors: sequential not parallel integrations, refactor abstractions *before* the next provider not after, and pin a hard "will not do" list to keep scope honest.

### What this plan explicitly does NOT do

- Become a PSA, docs system, automation engine, CMDB of record, or client-facing portal.
- Write back to QBO (no invoice creation, no time-entry push) in this plan.
- Run remote Datto jobs (no script execution from the dashboard) in this plan.
- Add compliance dashboards, quoting, projects, vendor/license tracking, or internal wiki.
- Multi-user or client-tenant authentication (stays single-admin).
- Go to the public internet (stays LAN-only).

## Phases

Work is sequential. Each phase produces shippable value. Target total calendar is 5-7 months at a realistic solo-dev pace with Claude assistance; compresses to 3-4 months if the owner works on this full-time.

---

### Phase 0 — Foundations (≈3 weeks)

**Goal:** Make it safe to ingest financial + device-control credentials, make hooks provider-correct, and prepare the abstractions so Datto and QBO slot in cleanly.

**0.1 Off-host backup automation (critical)**
- New script `deploy/backup.sh` that `sqlite3 .backup`s `backend/data/metrics.db` and copies `.vault_master_key` + `.session_signing_key` to a second location (NAS share or another VM).
- systemd timer unit `deploy/psa-dashboard-backup.timer` (daily).
- Document restore procedure in `deploy/SECRETS-DEPLOYMENT.md`.
- Current file: none. Risk: single VM failure loses everything.

**0.2 Data-correctness: provider-scope post-sync hooks**
- `backend/app/sync/hooks.py` currently runs `backfill_resolution_time`, `sync_billing_config`, `generate_billing_flags` globally with no `WHERE provider = ?` clause. When SuperOps syncs after Zendesk, it can overwrite Zendesk state.
- Change `run_post_sync_hooks(provider)` to pass `provider.get_provider_name()` to each hook and add `AND provider = ?` (or `AND t.provider = ?`) to every mutating query in `hooks.py`.

**0.3 Admin-setup race fix**
- `backend/app/api/routes_auth.py` `/api/auth/setup` does check-then-create on `any_admin_exists()`. Two concurrent requests can both create admins.
- Wrap in a single SQLite transaction or add a `UNIQUE(role)` constraint so the second insert fails atomically.

**0.4 Filter context refactor (frontend)**
- `frontend/src/context/FilterContext.tsx` today exposes a single global filter state assuming ticket shape (priority, provider toggle, corp). Datto and QBO pages will have different filter domains.
- Split into `TicketFilterContext`, and add a thin base `useDateRangeFilter` hook reusable across all domains. Leave existing ticket pages untouched (they keep the richer context).
- Parameterize `frontend/src/components/Layout.tsx:10-20` nav array so future sections are config-driven.

**0.5 New provider abstractions (backend, skeletons only)**
- `backend/app/billing/base.py` — `BillingProvider` ABC with `list_customers()`, `list_invoices()`, `list_payments()`, `list_time_activities()`, `get_ar_aging()`. Parallel to `psa/base.py`.
- `backend/app/rmm/base.py` — `RMMProvider` ABC with `list_sites()`, `list_devices(site_uid)`, `get_device(uid)`, `list_open_alerts(site_uid)`, `list_audits(device_uid)`. Parallel to `psa/base.py`.
- `backend/app/billing/factory.py` and `backend/app/rmm/factory.py` — mirror `psa/factory.py`'s async vault-pulling pattern.
- Add `mock.py` implementations so sync engine can be exercised without credentials.
- Add `billing.*` and `rmm.*` keys to `backend/app/vault/keys.py` so Settings UI discovers them automatically.
- Extend `backend/app/config.py` `Settings` with `billing.providers: list[str]` and `rmm.providers: list[str]`.

**0.6 CI pipeline**
- New `.github/workflows/test.yml`: Python 3.11 + 3.12, `pip install -r backend/requirements.txt`, run `pytest backend/tests/`. Also `npm ci && npm run build && npx tsc --noEmit` for the frontend.
- Fail the workflow on any test failure or TS error. Nothing fancy — this is the seatbelt.

**0.7 Real health checks**
- Extend existing `/health` in `backend/app/api/routes_sync.py` to probe: (a) DB writable (SELECT 1 + BEGIN/ROLLBACK), (b) vault decrypt roundtrip, (c) each active provider's credentials reachable (skip on vault-empty). Return 503 if any fail.
- Add `/livez` (process up only) and `/readyz` (DB + vault) for possible future nginx upstream health.

**0.8 Fix hooks.py provider scoping + filter duplication cleanup**
- Already covered in 0.2 for correctness.
- While in there, extract `_build_filter_sql` into a single `backend/app/api/dependencies.py:build_where_clause` used by all routes (today it's duplicated in `routes_overview.py`, `routes_alerts.py`, `routes_phone.py`, `routes_queue.py`).

**Deliberately deferred from the security review:**
- CORS wildcard, session cookie Secure flag, X-Forwarded-For rate-limit spoof, no CSRF token: all internet-exposure issues. LAN-only deployment makes these low priority. Document the LAN-only assumption in `deploy/SECRETS-DEPLOYMENT.md` so we don't flip to internet exposure without revisiting these.
- Prometheus metrics + Sentry error reporting: nice-to-have, not ship-blocking for an internal tool.

**Verification for Phase 0:**
- `pytest backend/tests/` green; CI workflow passes on a test PR.
- Manually trigger `deploy/backup.sh`, verify backup file exists on second host; simulate restore from backup into a scratch dir and confirm vault unlocks.
- Create two admin accounts concurrently via `curl -X POST /api/auth/setup &` — only one succeeds.
- Run a full SuperOps + Zendesk sync and inspect `billing_flags` and `resolution_time` rows — each has the correct `provider` value, no cross-contamination.
- Visit `/health` — returns 200 when healthy, 503 when vault master key is missing.

---

### Phase 1 — Correlation Layer (≈4 weeks)

**Goal:** One `companies` row per real customer, stitched across all systems. Same pattern for `people` and `assets`. This is the single most leveraged investment in the plan — every subsequent page gets simpler.

**1.1 Schema (new module `backend/app/identity/`)**
- New tables in `backend/app/database.py`:
  - `companies(id INTEGER PK, name, primary_domain, primary_phone, status, type, created_at, updated_at)`
  - `people(id INTEGER PK, display_name, primary_email, phone, is_internal_tech, company_id FK, created_at, updated_at)`
  - `assets(id INTEGER PK, company_id FK, name, primary_mac, serial, os, status, last_seen_at, created_at, updated_at)`
  - `entity_links(entity_type, entity_id, system, external_id, raw_payload JSON, last_seen_at, link_method, confidence, PRIMARY KEY(entity_type, system, external_id))` + index on `(entity_type, entity_id)`.
  - `attribute_overrides(entity_type, entity_id, attribute, value, pinned_by, pinned_at)` — per-row source-of-truth pins.
- New dataclasses in `backend/app/models.py`: `Company`, `Person`, `Asset`, `EntityLink`.

**1.2 Resolver module**
- `backend/app/identity/matcher.py` — scoring functions (domain exact match > 0.95, Jaro-Winkler name, token Jaccard for multi-word names).
- `backend/app/identity/resolver.py` — given a provider entity (e.g. a SuperOps client payload), returns `(company_id, confidence)` or `None` if below auto-link threshold.
- `backend/app/identity/precedence.py` — per-attribute source-of-truth rules (QBO wins company name + MRR, Datto wins device count, SuperOps wins primary domain, Zoom wins primary phone; always overrideable via `attribute_overrides`).
- `backend/app/identity/service.py` — high-level `link()`, `unlink()`, `split()`, `merge()`, `suggest()` operations with audit logging.
- Thresholds: auto-link ≥0.92, queue for review 0.70-0.91, create-new below 0.70.

**1.3 Sync-engine post-hook**
- After each provider sync, `backend/app/sync/engine.py` calls `identity.service.reconcile(provider_name)` which walks unmapped external IDs and either auto-links, queues, or creates new master rows. Idempotent.

**1.4 Backfill**
- One-time migration in `backend/app/database.py` migrations: for each existing SuperOps/Zendesk client, create a `companies` row and an `entity_links` row pointing to the prefixed ID. Technicians similarly — seed `people` from `tech_merge_map` so merged techs become single `people` rows.
- Strategy: phase 1 keeps legacy queries working via a SQL view that maps new master tables back to legacy prefixed IDs; phase 2 (in later plan revisions) cuts over.

**1.5 API routes**
- New `backend/app/api/routes_identity.py`:
  - `GET /api/companies` — paginated list with filters.
  - `GET /api/companies/{id}/aggregate` — master record + all linked external IDs + per-tab counts (tickets open, devices total, invoices unpaid, calls last 30d).
  - `POST /api/identity/link`, `/reject`, `/split`, `/merge` — all require `require_admin`.
  - `GET /api/identity/suggestions` — queued potential matches with confidence.
  - `PATCH /api/companies/{id}/pin` — pin an attribute to a specific source.

**1.6 Mapping UI (frontend)**
- New page `frontend/src/pages/IdentityMapping.tsx` under Settings: two-column "unmatched vs suggested" with confidence %, accept/reject/manual buttons, bulk operations.
- New `frontend/src/pages/CompanyDetail.tsx` replacing `ClientDetail.tsx` — master header + tabs (Tickets, Devices, Invoices, Calls, Contacts, Timeline). Each tab queries the aggregate endpoint.
- Route `/companies/:id` replaces `/clients/:id`; keep legacy redirect.

**1.7 Caller-ID → company resolution**
- Extend `backend/app/sync/phone_engine.py` (or create if absent) post-sync step: for each Zoom call with a non-internal `caller_number`, look up `people` by phone (or `companies` by normalized phone), populate `phone_calls.client_id` (which is already a column per the schema review — just unused).
- Fallback: substring match against company primary phone.
- New `frontend/src/components/IncomingCallCard.tsx` — on a hypothetical "live" panel, shows caller + their company + open tickets + MRR (MRR added in Phase 3).

**Critical files modified in Phase 1:**
- `backend/app/database.py` (add tables + migration)
- `backend/app/models.py` (new dataclasses)
- `backend/app/identity/*` (new module)
- `backend/app/sync/engine.py` (post-hook reconcile call)
- `backend/app/sync/phone_engine.py` (caller-ID resolution)
- `backend/app/api/routes_identity.py` (new)
- `backend/app/api/main.py` (wire router)
- `frontend/src/pages/IdentityMapping.tsx`, `CompanyDetail.tsx` (new/refactored)
- `frontend/src/components/Layout.tsx` (add nav entry)
- `frontend/src/api/hooks.ts` + `frontend/src/api/identity.ts` (new hooks file)

**Also in Phase 1 (shippable value that doesn't need Datto or QBO):**
- Expiring-contracts alerts: extend `backend/app/alerts/engine.py` with a rule that scans `client_contracts.end_date` for 30/60/90-day-out expirations, shows on Overview + Contracts pages. No new integrations needed.

**Verification for Phase 1:**
- Seed a scratch DB with 3 SuperOps clients + 2 Zendesk clients where 1 Zendesk client name matches a SuperOps client. Run reconcile. Verify 4 `companies` rows exist with correct link rows.
- Trigger the Settings mapping UI: suggest a candidate link, accept it, verify `entity_links` updates and confidence stored.
- Call `/api/companies/{id}/aggregate` — returns counts across all linked systems.
- Make a test call from a known client's number to a Zoom user — after next phone sync, `phone_calls.client_id` populated and the CompanyDetail Calls tab shows it.

---

### Phase 2 — Datto RMM Integration (≈6 weeks)

**Goal:** Device inventory, online/offline, patch compliance, alerts — all per client via the correlation layer.

**2.1 Datto provider implementation**
- `backend/app/rmm/datto.py` — thin `httpx.AsyncClient` against Datto REST v2. No SDK (drmmsdk is unmaintained). Implements `RMMProvider` ABC from Phase 0.5.
- Token cache + OAuth refresh (100h tokens), offset pagination iterator (max 250/page), 429 back-off, region-aware base URLs (Pinotage/Merlot/Concord/Vidal/Zinfandel/Syrah; store as `rmm.datto.platform` config).
- Credentials in vault: `rmm.datto.api_key`, `rmm.datto.api_secret`, `rmm.datto.platform`.

**2.2 Database + sync**
- New tables: `sites` (Datto equivalent of a client), `devices`, `rmm_alerts`, `device_audits` (hardware/software inventory snapshots). All prefixed `datto:` and with a `provider` column to match the existing convention.
- Extend `backend/app/sync/manager.py` to coordinate PSA + RMM + (future) Billing engines. Generalize it so adding a sync kind is a one-line registration.
- Sync intervals: devices every 15min (matches PSA), alerts every 5min (tighter), audits every 6h (audits lag 24h upstream anyway).

**2.3 Identity integration**
- Sync engine post-hook calls `identity.service.reconcile("datto")` — maps Datto Sites to `companies`, devices to `assets`.
- Mapping UI (from Phase 1) surfaces Datto sites with suggestions.

**2.4 API routes**
- `backend/app/api/routes_rmm.py`:
  - `GET /api/rmm/overview` — KPIs: total devices, online count, offline >24h count, patch-compliant %, active alerts.
  - `GET /api/rmm/devices` — filterable list.
  - `GET /api/rmm/alerts` — open alerts with company/device context.
  - `GET /api/companies/{id}/devices` — company-scoped (reuses aggregate endpoint).

**2.5 Frontend pages**
- `frontend/src/pages/Devices.tsx` — device inventory with online/offline indicator, last-seen, patch status, OS.
- `frontend/src/pages/Patches.tsx` — patch compliance rollup + EOL OS counts (Win10 EOL Oct 2025, etc.).
- `frontend/src/pages/Alerts.tsx` — active RMM alerts, grouped by site, with deduplication.
- Add Devices tab to `CompanyDetail.tsx` (already stubbed in Phase 1).
- New KPI cards on Overview: "devices offline >24h", "patch compliance %", "open RMM alerts".

**Deferred:**
- Datto BCDR (separate API) — future `BackupProvider` abstraction.
- Running remote jobs/scripts — write-back, explicitly out of scope this plan.
- Custom monitor normalization — just store `alertContext` raw JSON for now.

**Critical files:**
- `backend/app/rmm/datto.py`, `mock.py`, `factory.py`
- `backend/app/database.py` (new tables)
- `backend/app/sync/rmm_engine.py` (new)
- `backend/app/sync/manager.py` (register RMM)
- `backend/app/api/routes_rmm.py` (new)
- `backend/app/vault/keys.py` (datto keys)
- `frontend/src/pages/Devices.tsx`, `Patches.tsx`, `Alerts.tsx` (new)
- `frontend/src/api/rmm.ts` (new hooks)

**Verification:**
- With mock provider only: device list loads, filter/sort works, company drill-down shows correct devices.
- With real Datto key: full initial sync completes in <10min for typical MSP (~1-2k devices), incremental sync in <1min.
- Disable a test site's agent → within 15min the device shows offline in the dashboard.
- Pull API for 30min with rate-limited credentials — verify 429 back-off behaves.

---

### Phase 3 — QuickBooks Online Integration (≈7 weeks)

**Goal:** Invoices, AR aging, payments, time activities, per-client profitability.

**3.1 QBO provider implementation**
- `backend/app/billing/quickbooks.py` — `httpx.AsyncClient` against v3 REST with `minorversion=75`. No SDK (`python-quickbooks` is sync; fights FastAPI).
- OAuth2 flow: interactive connect step added to Settings (Intuit requires a browser redirect), stores `qbo.access_token`, `qbo.refresh_token`, `qbo.realm_id`, `qbo.token_expires_at`, `qbo.reconnect_url` in vault.
- **Refresh-token serialization:** per-realm asyncio.Lock so two concurrent syncs don't race a refresh (concurrent refresh = disconnect storm). Non-negotiable.
- Deadline: implement the reconnect URL page by Feb 2026 per Intuit's Nov 2025 policy change.

**3.2 Database + sync**
- New tables: `qbo_customers`, `invoices` (line items denormalized), `payments`, `time_activities`, `accounts` (chart of accounts minimal).
- CDC polling with 30-day window; full-sync fallback beyond 30 days.
- Sync interval: 30min for invoices/payments, 6h for customers/accounts.
- Webhook receiver `backend/app/api/routes_qbo_webhook.py` for invoice/payment events — treat as hints, reconcile on poll (webhooks unreliable per research).

**3.3 Identity integration**
- Post-sync reconcile maps `qbo_customers` → `companies`. Parent/sub-customer hierarchy supported: sub-customer becomes a `company.parent_id` relationship or a `site` under a parent company (decide in Phase 3 kickoff).

**3.4 API routes**
- `backend/app/api/routes_billing.py` (existing file, extend):
  - `GET /api/billing/ar-aging` — buckets 0-30, 31-60, 61-90, 90+, per-company drill-down.
  - `GET /api/billing/unbilled-time` — PSA time entries not linked to any QBO invoice line.
  - `GET /api/billing/profitability?client_id=&period=` — revenue (QBO paid invoices) minus tech cost (PSA worklog hours × `billing.tech_cost_per_hour`), per company per period.
- `GET /api/companies/{id}/invoices` — company-scoped invoices.

**3.5 Frontend pages**
- `frontend/src/pages/ARAging.tsx` — buckets + drill-down table + aging trend chart.
- `frontend/src/pages/Profitability.tsx` — per-client scorecard table (revenue, cost, margin, margin %, trend), sortable by margin to surface unprofitable clients.
- `frontend/src/pages/UnbilledTime.tsx` — PSA hours without matching invoice lines, grouped by client + tech, "last worked" column.
- Add Invoices tab to `CompanyDetail.tsx`.
- New KPI cards on Overview/Executive: total AR, >60 day AR, MTD revenue, MTD margin.

**3.6 Final feature integration**
- Incoming-call card now shows caller's MRR (from QBO paid invoices / subscription items) alongside open-ticket count.
- Expiring-contracts alerts correlate with QBO recurring transactions when available.

**Deferred (explicitly):**
- Write-back (creating/voiding invoices, pushing time entries). Future plan.
- Multi-currency handling.
- Class tracking (requires QBO Plus/Advanced subscription anyway).
- Avalara/sales tax detail views.

**Critical files:**
- `backend/app/billing/quickbooks.py`, `mock.py`, `factory.py`
- `backend/app/database.py` (new tables, CDC cursor table)
- `backend/app/sync/billing_engine.py` (new)
- `backend/app/api/routes_billing.py` (extend)
- `backend/app/api/routes_qbo_oauth.py` (new — handles Intuit's redirect callback and reconnect-url page)
- `backend/app/api/routes_qbo_webhook.py` (new)
- `frontend/src/pages/ARAging.tsx`, `Profitability.tsx`, `UnbilledTime.tsx` (new)
- `frontend/src/api/billing.ts` (new hooks)
- `frontend/src/pages/Settings.tsx` (QBO connect button)

**Verification:**
- With mock provider: AR aging buckets look correct, profitability math checks out against hand-calculation for 2 test clients.
- With real QBO sandbox: OAuth connect succeeds, initial sync of 100 test invoices completes, incremental CDC detects new invoice within 30min.
- Disconnect scenario: revoke QBO app, verify dashboard degrades gracefully (shows stale data + banner + reconnect button, doesn't crash).
- Refresh token race: trigger two concurrent syncs from scheduler + manual; verify only one refresh request, tokens stay valid.

---

### Phase 4 — Leaderboards + Call-Context Polish (≈2 weeks)

**Goal:** Finish the four features the owner picked; polish the incoming-call surface into a genuinely useful tool.

- Leaderboards: tech call volume, avg duration, answer rate (extends existing phone analytics), cross-system — ties a tech's call metrics to their ticket metrics via `people` master record.
- Live-ish "incoming calls" panel on Overview: last 2h of calls, each with client link, open-ticket count, MRR, last call date. Polls every 60s.
- Expiring contracts: email/Slack digest (when we add SMTP config in vault) — until then, just UI + banner.
- Profitability deep-dive: 6-month trend chart per client, filterable leaderboard by margin %.

**Critical files:**
- `frontend/src/pages/Overview.tsx` (add incoming-calls panel)
- `frontend/src/pages/Technicians.tsx`, `PhoneAnalytics.tsx` (enriched leaderboards)
- `backend/app/api/routes_phone.py`, `routes_technicians.py` (cross-system queries via `people` joins)
- `backend/app/alerts/engine.py` (expiring-contracts rule from Phase 1 gets notification channel added)

**Verification:**
- Make a real inbound test call from a known client phone — within 90s, appears on Overview incoming-calls panel with correct client + open-ticket count.
- Compare tech leaderboard (dashboard) against Zoom's own report for a 7-day window — numbers match within rounding.

---

## Cross-cutting conventions (apply to every phase)

- **No em dashes** anywhere in code, UI, or comments (existing CLAUDE.md rule). This roadmap doc is exempt.
- **No provider-specific code** outside `psa/*.py`, `phone/*.py`, new `billing/*.py`, new `rmm/*.py`.
- **All paths via `pathlib`** (existing rule).
- **Credentials only via vault** (existing rule). New keys register in `backend/app/vault/keys.py` first.
- **Admin routes use `require_admin`**; read endpoints stay public on the LAN.
- **No mocks in tests that hit real DB**; use `tmp_path` SQLite from the existing conftest pattern.
- **Every new provider gets ≥15 tests** covering auth, rate limit, pagination, error shape, and a full-sync mock.
- **Abstractions second, not first** — the second implementation is what reveals whether the base class is right. Skeletons in Phase 0 are committed; they can flex through Phase 2/3 before being considered frozen.

## Testing baseline to maintain

The existing 89 tests cover vault + auth well. Each phase adds minimum:

- Phase 0: +10 tests (hook provider-scope correctness, admin-setup race, new abstraction skeletons exercise).
- Phase 1: +25 tests (matcher scoring, resolver thresholds, link/unlink/merge/split idempotency, backfill correctness).
- Phase 2: +20 tests (Datto mock provider, sync engine with RMM, company-device aggregation).
- Phase 3: +25 tests (QBO mock, OAuth refresh serialization, AR aging math, profitability math, CDC cursor handling).
- Phase 4: +5 tests (leaderboard queries cross-system join correctness).

Target: ~175 backend tests by end of Phase 4. Green on CI for every merged change.

## Ongoing risks the plan acknowledges

- **Bus factor = 1.** Claude-assisted code still needs a human who understands it. Keep ADR-style one-paragraph notes in `docs/decisions/` for each non-trivial library or pattern choice.
- **API churn.** Every vendor can break us quarterly. Keep `mock.py` for every provider current — it's the seatbelt that lets us replace a provider without replacing the dashboard.
- **LAN-only assumption.** Documented in `deploy/SECRETS-DEPLOYMENT.md`. If this ever goes internet-exposed, the deferred security items (CORS allowlist, Secure cookie, XFF validation, CSRF) become blockers and must be fixed in a dedicated pre-exposure sprint.
- **SQLite ceiling.** Fine for current scale and the next 2-3 years. When the portal passes ~100K devices or multi-user access is added, plan a Postgres migration through the existing DAL — keep all queries parameterized so the swap stays mechanical.

## End-to-end verification checklist

After Phase 4 completes, the dashboard should pass this manual test on the live LAN install:

1. `sudo bash update.sh` completes cleanly; service starts.
2. `/health` returns 200 with all providers green.
3. CI workflow on the most recent commit is green.
4. `deploy/backup.sh` on schedule; a sample restore into a scratch dir succeeds.
5. Open Overview — see KPI cards for tickets, SLA, devices offline, AR, MTD margin, incoming calls in last 2h, expiring contracts.
6. Click through to a known client (CompanyDetail) — see tickets + devices + invoices + calls + contacts unified.
7. Make a test call from a known client — it appears on Overview's incoming-calls panel within 90s with correct client context.
8. Check AR aging — totals match QBO's own aging report.
9. Check profitability scorecard — top unprofitable client looks plausible vs gut check.
10. In Settings → Identity Mapping — there are no >0.7-confidence unmapped entities sitting ungroomed.
