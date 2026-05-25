# Credit Tracker Project Overview

## Goal

Credit Tracker is a local personal finance app for importing credit card and checking activity, sorting transactions, tracking work expenses, and analyzing personal spending.

The main workflow is intentionally staged:

1. Import statement data and preview what will be added.
2. Sort new debit transactions as `personal` or `work`.
3. Categorize personal spending for dashboard and spending breakdowns.
4. Mark work transactions as expensed when they have been reimbursed or submitted.

The installed desktop app keeps a no-login user experience, but API access is still session-based. The desktop shell performs a one-time local token bootstrap during startup.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, SQLite, Pydantic settings, Starlette sessions, bcrypt.
- Frontend: React, Vite, TypeScript, TanStack Query, Zustand, Recharts, Tailwind CSS.
- Desktop shell: Tauri 2, Rust, WebView2, PyInstaller backend sidecar, Inno Setup installer.
- Storage: SQLite.
- Money values are stored as integer cents.

## Run Modes

### Desktop App

The packaged app starts a PyInstaller-bundled FastAPI sidecar on a free local port, then the Tauri shell navigates WebView2 to the backend after a secure bootstrap.

Runtime flow:

1. `packaging/backend_entry.py` chooses a free port.
2. The sidecar generates a per-run token and sets `DESKTOP_AUTH_TOKEN`.
3. The sidecar writes `%APPDATA%\CreditTracker\runtime.json` containing only `{ port, token }`.
4. `desktop/src-tauri/src/lib.rs` reads and deletes `runtime.json`.
5. Tauri navigates to `GET /desktop-login?token=...`.
6. The backend validates and consumes the token, provisions or loads the local user, sets the signed session cookie, and redirects to `/`.
7. Normal `/api/v1/*` routes use `get_current_user`; desktop mode does not bypass route auth.

Desktop data and logs:

- Database: `%APPDATA%\CreditTracker\credit_tracker.db`.
- Shell debug log: `%APPDATA%\CreditTracker\shell.log`.
- Runtime metadata: `%APPDATA%\CreditTracker\runtime.json`, short-lived and deleted after launch.

Build the installer from the repo root:

```powershell
./packaging/build.ps1
```

### Developer Mode

Run the app locally with hot reload:

```powershell
./start.ps1
```

The script creates or reuses the backend virtual environment, installs backend dependencies when needed, runs Alembic migrations through the seed step, starts FastAPI on `http://127.0.0.1:8012`, and starts Vite on `http://127.0.0.1:5175`.

Developer database:

- `credit_tracker.db` in the repo root.

Login credentials are set on first run via `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend/.env`. See [README.md](README.md) for setup.

## Authentication And Security

Browser/developer mode uses username/password login with signed session cookies.

Login protection:

- Failed login attempts return `401`.
- Repeated failed attempts are rate limited with `429`.
- Successful login clears the failure counter.
- Settings live in `backend/app/config.py`:
  - `LOGIN_RATE_LIMIT_ATTEMPTS`
  - `LOGIN_RATE_LIMIT_WINDOW_SECONDS`

Desktop mode uses the `/desktop-login` bootstrap route instead of showing a login screen. The token is per run, one-time-use, and only enabled when `desktop_mode` is true.

Tauri uses a restrictive content security policy in `desktop/src-tauri/tauri.conf.json`; asset CSP modification and JS eval navigation are disabled.

## Main User Flows

### Import

Imports are handled by the shared service in `backend/app/services/transaction_import_service.py`.

Supported flows:

- Credit card preview and confirm.
- Checking preview and confirm.
- Duplicate detection via `source_hash`.
- 10 MB upload limit enforced while reading the stream, even when the client does not provide a reliable size.
- Card payment credits such as `PAYMENT - THANK YOU` and `PAYMENT RECEIVED - THANK YOU` are ignored for card imports.
- Refunds and other credits are preserved.
- Checking imports default to `classification = "personal"`.

Key endpoints:

- `POST /api/v1/transactions/import/preview`
- `POST /api/v1/transactions/import/confirm`
- `POST /api/v1/transactions/checking/import/preview`
- `POST /api/v1/transactions/checking/import/confirm`

### Inbox

Route: `/inbox`

The Inbox shows uncategorized debit transactions where `classification` is `null`.

Users can mark transactions as:

- `personal`
- `work`

### Personal Inbox

Route: `/personal-inbox`

The Personal Inbox shows personal debit transactions where `personal_category` is `null`.

Users can assign categories such as Groceries, Dining, Transportation, Home, Health, Subscriptions, Shopping, Travel, Entertainment, Personal Care, Gifts, Other, and Transfer.

`Transfer` is special: it is excluded from personal spending totals, dashboard personal totals, and personal CSV export. It is valid for both debit and credit transactions.

Categories are saved through:

```http
PUT /api/v1/transactions/{id}
```

Example:

```json
{ "personal_category": "Dining" }
```

### Spending

Route: `/spending`

The Spending page shows monthly personal debit spending:

- Total personal spending.
- Average monthly personal spending.
- Monthly bar chart.
- Selected-month category breakdown.
- Whole-range category breakdown.

Data comes from:

```http
GET /api/v1/transactions/spending/personal?months=12
```

Uncategorized personal spending is grouped as `Uncategorized`. Personal debits with `personal_category = "Transfer"` are excluded.

### Work Expense Tracking

Work transactions can be marked as expensed. Only work transactions may have `expensed = true`.

## Data Model

`transactions` stores:

- `transaction_date`
- `description`
- `amount_cents`
- `transaction_type`
- `classification`
- `personal_category`
- `expensed`
- `statement_format`
- `source_hash`
- `imported_at`
- `updated_at`

`classification` supports:

- `personal`
- `work`
- `null`

When a transaction is changed away from `personal`, its `personal_category` is cleared. When a transaction is changed away from `work`, its `expensed` flag is cleared.

## Migrations

Alembic is the canonical schema migration path.

Key files:

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260525_0001_initial_schema.py`
- `backend/app/migrations.py`

Startup calls `run_migrations()` from `backend/app/main.py`. The seed script also runs migrations before creating the default user.

Run migrations manually:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The initial migration can create an empty SQLite database and can also upgrade older local databases that are missing `expensed` or `personal_category`.

## Important Backend Endpoints

- `GET /health`
- `GET /desktop-login?token=...`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/transactions`
- `PUT /api/v1/transactions/{tx_id}`
- `POST /api/v1/transactions/bulk-classify`
- `POST /api/v1/transactions/import/preview`
- `POST /api/v1/transactions/import/confirm`
- `GET /api/v1/transactions/spending/personal`
- `GET /api/v1/transactions/dashboard`
- `GET /api/v1/transactions/export/{classification}`

## Important Files

Backend:

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/dependencies.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/desktop.py`
- `backend/app/routers/transactions.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/desktop_auth_service.py`
- `backend/app/services/statement_import_service.py`
- `backend/app/services/transaction_import_service.py`

Frontend:

- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/InboxPage.tsx`
- `frontend/src/pages/PersonalInboxPage.tsx`
- `frontend/src/pages/SpendingPage.tsx`
- `frontend/src/pages/TransactionsPage.tsx`
- `frontend/src/components/ImportModal.tsx`
- `frontend/src/api/auth.ts`
- `frontend/src/api/transactions.ts`
- `frontend/src/types.ts`

Desktop and packaging:

- `packaging/backend_entry.py`
- `packaging/backend.spec`
- `packaging/build.ps1`
- `packaging/installer.iss`
- `desktop/src-tauri/src/lib.rs`
- `desktop/src-tauri/tauri.conf.json`

## Tests And Checks

Backend flow tests live in:

```text
backend/tests/test_backend_flows.py
```

Coverage includes auth/session requirements, login rate limiting, desktop token bootstrap, import preview/confirm behavior, upload size enforcement, migrations, classification, personal categories, dashboard data, spending data, and exports.

Common verification commands:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
.\backend\.venv\Scripts\python.exe -m alembic upgrade head
.\backend\.venv\Scripts\python.exe -m pip_audit
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run audit
cargo check --manifest-path desktop\src-tauri\Cargo.toml
cargo audit --manifest-path desktop\src-tauri\Cargo.toml
```

GitHub Actions CI is defined in `.github/workflows/ci.yml` and runs backend tests, `pip-audit`, frontend lint/build/audit, `cargo check`, and `cargo audit`.
