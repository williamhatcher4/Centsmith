# Centsmith Project Overview

## Goal

Centsmith is a local personal finance app for importing credit card and checking activity, sorting transactions, tracking work expenses, and analyzing personal spending.

The main workflow is intentionally staged:

1. Import statement data and preview what will be added.
2. Sort new debit transactions as `personal` or `work`.
3. Categorize personal spending for dashboard and spending breakdowns.
4. Mark work transactions as expensed when they have been reimbursed or submitted.

The installed desktop app keeps a no-login user experience, but API access is still session-based. The desktop shell performs a one-time local token bootstrap during startup.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, SQLite, Pydantic settings, Starlette sessions, bcrypt.
- Frontend: React 19, Vite, TypeScript, TanStack Query, Zustand, Recharts, Tailwind CSS.
- Desktop shell: Tauri 2, Rust, WebView2, PyInstaller backend sidecar, NSIS installer (Tauri bundler).
- Storage: SQLite.
- Testing: pytest, Vitest + Testing Library + MSW, Playwright, `cargo test`.
- Money values are stored as integer cents.

## Run Modes

### Desktop App

The packaged app starts a PyInstaller-bundled FastAPI sidecar on a free local port, then the Tauri shell navigates WebView2 to the backend after a secure bootstrap.

Runtime flow:

1. `packaging/backend_entry.py` chooses a free port.
2. The sidecar generates a per-run token and sets `DESKTOP_AUTH_TOKEN`.
3. The sidecar writes `%APPDATA%\Centsmith\runtime.json` containing only `{ port, token }`.
4. `desktop/src-tauri/src/lib.rs` reads and deletes `runtime.json`.
5. Tauri navigates to `GET /desktop-login?token=...`.
6. The backend validates and consumes the token, provisions or loads the local user, sets the signed session cookie, and redirects to `/`.
7. Normal `/api/v1/*` routes use `get_current_user`; desktop mode does not bypass route auth.

Desktop data and logs:

- Database: `%APPDATA%\Centsmith\centsmith.db`.
- Shell debug log: `%APPDATA%\Centsmith\shell.log`.
- Runtime metadata: `%APPDATA%\Centsmith\runtime.json`, short-lived and deleted after launch.
- Session-signing key: `%APPDATA%\Centsmith\secret.key.dpapi`, DPAPI-encrypted under the current Windows user. Legacy plaintext `secret.key` files are migrated and deleted on first run.

Build the installer from the repo root:

```powershell
# Local installer (PyInstaller backend, unsigned):
./packaging/build.ps1

# Release backend bundle (PyArmor-obfuscated, only useful with CI signing):
./packaging/build.ps1 -SkipTauri -ObfuscateBackend
```

### Developer Mode

Run the app locally with hot reload:

```powershell
./start.ps1
```

The script creates or reuses the backend virtual environment, installs backend dependencies when needed, runs Alembic migrations through the seed step, starts FastAPI on `http://127.0.0.1:8012`, and starts Vite on `http://127.0.0.1:5175`.

Developer database:

- `centsmith.db` in the repo root.

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

Secrets at rest:

- The session-cookie signing key (`Settings.secret_key`) is generated lazily in `backend/app/config.py:_default_secret_key`. In development it is the static `dev-centsmith-change-me`.
- In frozen Windows builds it is persisted as `%APPDATA%\Centsmith\secret.key.dpapi`, encrypted with `CryptProtectData` (DPAPI, user scope, no entropy). The key cannot be decrypted by another Windows user or off the device.
- On a decrypt failure (different user profile, restored from a non-DPAPI backup) the key is rotated automatically and a one-line warning is written to stderr. Existing sessions are invalidated; the app keeps running.
- File creation uses `O_EXCL` so a lost race re-reads the winner's value rather than overwriting.

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

## CI Toolchain Pins And Dependency Audits

CI fails on audit findings and on toolchain changes even when no app code changes. Read this before you change a workflow or update dependencies.

Pinned versions. Change them on purpose, and run the full CI suite after each change:

- **Node 24.** `actions/setup-node` uses `node-version: "24"` in `ci.yml` and `release.yml`. Don't use `lts/*`. When `lts/*` moved to Node 26, Node's built-in Web Storage replaced jsdom's `localStorage` in Vitest. Without `--localstorage-file` it is undefined there, and 133 frontend tests failed.
- **Ubuntu 24.04.** The Linux jobs in `ci.yml` and `update-contract.yml` use `runs-on: ubuntu-24.04`. Don't use `ubuntu-latest`. When `ubuntu-latest` moved to 26.04, Playwright 1.60 could no longer install Chromium's system libraries (`playwright install --with-deps`).
- **Windows not pinned.** The backend job and the release job still use `windows-latest`.

Local tooling:

- Use Node 24 and the npm 11 that ships with it. npm 10 crashes on this dependency tree with `Cannot read properties of null (reading 'edgesOut')` during `npm audit fix` and `npm update`.
- On Node 22, `DataDiagnosticsCard.test.tsx` › "downloads a backup in the browser build" fails. Node's `fetch` can't read jsdom's `Blob` (`object.stream is not a function`). It passes on Node 24, which is what CI uses.

Dependency audits. CI runs these gates:

- `pip-audit` for the backend.
- `npm audit --audit-level=moderate` for `frontend/`.
- `cargo audit` for `desktop/src-tauri`.

`e2e/package-lock.json` is not audited.

New advisories turn CI red without any code change. Fix them with targeted updates, not blanket upgrades:

- **Rust:** `cargo update -p <crate>`. A plain `cargo update` touches hundreds of crates. Leave the `unmaintained`, `unsound` and `yanked` warnings; they don't fail the job.
- **npm:** `npm audit fix` keeps updates inside the ranges in `package.json`. Avoid `npm audit fix --force`, which can apply breaking downgrades. For example, it would move ESLint 10 to 9.

Current workarounds and follow-ups:

- **minimatch override.** `frontend/package.json` has `"overrides": { "minimatch": "^11.0.5" }`. The advisory fix (GHSA-g3hv-75wg-m249) only exists in minimatch 11, but `eslint` 10, `@eslint/config-array` and `typescript-eslint` 8 still require `^10`. Only the lint toolchain uses minimatch. Remove the override once those packages depend on minimatch 11.
- **Tauri bump.** Clearing the `zip` advisories required `tauri-plugin-updater` 2.14.1 (`zip` 9). That version needs `tauri` 2.12.5, up from 2.11.2. The change was verified with `cargo check`, `cargo test` and `cargo audit` on Linux only. Before the next release, build the installer on Windows and check launch, the startup handshake and the update prompt.
- **Generated schemas.** Building the Rust shell regenerates `desktop/src-tauri/gen/schemas/*` for the host platform. Commit regenerated schemas only from a Windows build. A Linux build adds `linux-schema.json`, which doesn't belong in the repo.

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

## Release Pipeline

Signed Windows releases are built by `.github/workflows/release.yml` on `v*` tags or `workflow_dispatch`. Installers and update manifests are published to a private Cloudflare R2 bucket and served through a license-gated Cloudflare Worker at `https://centsmith.ca/api/updates`. The Worker lives in a separate website repo.

Pipeline stages:

1. **CI gate.** The workflow calls `ci.yml` as a reusable workflow, so the full suite has to pass before anything is built: backend tests and coverage, `pip-audit`, frontend lint, tests, build and audit, `cargo check`, `cargo test`, `cargo audit`, and the Playwright e2e tests.
2. **Release notes.** The matching `## [x.y.z]` section of `CHANGELOG.md` is extracted and used as the release notes. A tag with no matching section fails the release on purpose.
3. **Credential checks.** The workflow fails early if the Cloudflare credentials are missing.
4. **Code-signing certificate.** If `WINDOWS_CERTIFICATE_BASE64` is configured, the PFX is decoded into the runner's temp directory. Otherwise Authenticode signing is skipped.
5. **Version injection.** The tag version (`vX.Y.Z`) is written into `desktop/src-tauri/tauri.conf.json`. The committed version stays at `0.1.0` as a placeholder; CI is the only place it changes.
6. **Backend bundle.** `packaging/build.ps1 -SkipTauri -ObfuscateBackend` runs. PyArmor obfuscates the sidecar and PyInstaller packs it. `packaging/validate-release-artifacts.ps1` then aborts the build if any `.env`, `.pfx`, `.p12`, `.pem` or `.key` file has slipped into the bundle, or any file named `private`, `credential`, `password`, `signing-key` or `signing_key`.
7. **Tauri shell.** The shell is built as an NSIS installer, each binary is signed with `packaging/sign-windows.ps1` when a certificate is configured, and the updater `.sig` file is generated.
8. **Publish to R2.** The workflow uploads:
   - the installer
   - `latest.json`, which feeds the website download page
   - a per-release metadata file plus a rolling `releases.json` holding the last 20 releases
   - `updater.json`, the Tauri updater manifest. Before upload it is checked against the updater schema, because a malformed feed would break auto-update for every install.
9. **Feed contract test.** `packaging/update-contract-test.ps1` checks that the live feed serves the new version and the exact installer bytes through the license gate. Without `CENTSMITH_TEST_LICENSE` it only checks that unlicensed requests are rejected. `.github/workflows/update-contract.yml` runs the same test weekly to catch regressions in the Worker.
10. **Installer smoke test.** `packaging/installer-smoke-test.ps1` installs the app on the runner, launches it, checks that `/health` responds, and uninstalls it.

Auto-update at runtime:

- `tauri-plugin-updater` polls `https://centsmith.ca/api/updates/latest.json` once the backend is reachable. The minisign public key committed in `tauri.conf.json` verifies update signatures.
- Updates are tied to the paid license. The shell reads `license.token` from the data directory and sends it as a bearer header. With no license stored, the update check is skipped and the app keeps working normally.
- The result of each check is written to `update-check.json`, with the license token removed, and shown in Settings (`GET /api/v1/maintenance/update-status`).
- If a newer version exists, the user is prompted. On accept, the installer runs in `quiet` mode, the backend sidecar is stopped cleanly, and the app restarts.
- The update prompt is only shown after `wait_for_port_open` succeeds, so it never appears before the app has loaded.

Required GitHub secrets:

- `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`: write access to the `centsmith-installers` R2 bucket.
- `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: the minisign keypair used to sign updater artifacts.
- Optional: `WINDOWS_CERTIFICATE_BASE64` and `WINDOWS_CERTIFICATE_PASSWORD`, the Authenticode PFX and its password. Leave them unset to publish unsigned installers.
- Optional: `CENTSMITH_TEST_LICENSE`, a test license for the full feed contract test.

For local signing on a developer workstation, import the PFX into the user's certificate store once and sign with `/sha1 <thumbprint>`. `packaging/sign-windows.ps1` explains the trade-off CI accepts by passing the password with `/p` on the command line.

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
- `packaging/sign-windows.ps1`
- `packaging/validate-release-artifacts.ps1`
- `packaging/update-contract-test.ps1`
- `packaging/installer-smoke-test.ps1`
- `desktop/src-tauri/src/lib.rs`
- `desktop/src-tauri/tauri.conf.json`
- `.github/workflows/release.yml`

## Tests And Checks

Backend tests live in `backend/tests/`. They cover:

- auth and session requirements, login rate limiting, and the desktop token bootstrap
- import preview and confirm, upload size limits, and parsing of a sample set of statement files in many formats (`tests/fixtures/corpus/`)
- import profiles, cards and statement cycles, backup and restore, and reporting
- migrations, including upgrading a database from an older released version (`test_migration_lineage.py`)
- an OpenAPI snapshot test that catches unintended API changes
- performance tests over a large synthetic ledger (the `perf` marker)

pytest enforces a coverage gate (`--cov-fail-under` in `backend/pyproject.toml`). The gate is only ever raised as coverage grows, never lowered.

Frontend unit and component tests use Vitest, Testing Library and MSW and sit next to the code as `*.test.ts(x)`. End-to-end tests in `e2e/tests/` use Playwright against a seeded backend.

Common verification commands:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
.\backend\.venv\Scripts\python.exe -m alembic upgrade head
.\backend\.venv\Scripts\python.exe -m pip_audit
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run test
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run audit
npm.cmd --prefix e2e test
cargo check --manifest-path desktop\src-tauri\Cargo.toml
cargo test --manifest-path desktop\src-tauri\Cargo.toml
cargo audit --manifest-path desktop\src-tauri\Cargo.toml
```

GitHub Actions CI (`.github/workflows/ci.yml`) runs all of the above on every pull request. The release workflow also calls it as a required first step.

Signed releases are produced by `.github/workflows/release.yml`; see the [Release Pipeline](#release-pipeline) section above.
