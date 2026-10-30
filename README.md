# Generate Report

A simple full-stack starter for a report-generation application. The current name is deliberately easy to change later: update the package and app display names when you choose the final name.

## Technology stack

- Backend: Python, FastAPI, SQLAlchemy
- Frontend: React with Vite
- Database: MySQL or Microsoft SQL Server (MSSQL), selected with environment configuration

## Folder structure

```text
generate-report/
├── backend/
│   ├── app/
│   │   ├── config/        # environment-backed settings
│   │   ├── controllers/   # request orchestration and error translation
│   │   ├── database/      # engine, sessions, base model
│   │   ├── models/        # SQLAlchemy models
│   │   ├── repositories/  # database queries
│   │   ├── routes/        # HTTP endpoints
│   │   ├── schemas/       # API request/response types
│   │   ├── services/      # business logic
│   │   ├── utils/         # shared helpers/errors
│   │   └── main.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/src/
│   ├── components/ pages/ services/ hooks/ utils/ config/ assets/
│   └── App.jsx
├── server.sh
└── .gitignore
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer and npm
- A running MySQL server **or** Microsoft SQL Server
- For MSSQL, an installed ODBC driver (the example uses `ODBC Driver 18 for SQL Server`)
- A running database server reachable from `backend/.env`

## Configure the database

Create a local backend environment file:

```bash
cd backend
cp .env.example .env
```

### MySQL example

Create a MySQL database and user, then use this configuration in `backend/.env`:

```env
DB_DIALECT=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=generate_report
DB_USER=report_user
DB_PASSWORD=your-password
```

### MSSQL example

Create a SQL Server database and login, then use:

```env
DB_DIALECT=mssql
DB_HOST=127.0.0.1
DB_PORT=1433
DB_NAME=generate_report
DB_USER=report_user
DB_PASSWORD=your-password
MSSQL_DRIVER=ODBC Driver 18 for SQL Server
```

## External Microsoft SQL Server

This copy does not start or manage SQL Server. Point `backend/.env` at an existing SQL Server instance and create the `generate_report` database and login using your organization’s database process. The backend uses SQLAlchemy, `pyodbc`, and ODBC Driver 18; keep `MSSQL_TRUST_SERVER_CERTIFICATE=false` for shared or production servers and configure the proper certificate trust chain.

Apply schema migrations before starting the application:

```bash
cd backend
.venv/bin/alembic upgrade head
```

To install the schema, SQL Server stored procedures, and all built-in demo
data in one idempotent command, run the seeder:

```bash
cd backend
.venv/bin/python seed.py
```

The seeder applies outstanding Alembic migrations first, then creates the
Companies A–C sample sales, clients, employees, and three payroll months.
Running it again does not duplicate the demo data. Stored procedures are
installed by the migrations when `DB_DIALECT=mssql`; MySQL does not support
the SQL Server procedure definitions used by this application.

### Installing ODBC Driver 18 on macOS

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew trust --formula microsoft/mssql-release/msodbcsql18
brew trust --formula microsoft/mssql-release/mssql-tools18
HOMEBREW_ACCEPT_EULA=Y brew install microsoft/mssql-release/msodbcsql18 microsoft/mssql-release/mssql-tools18
odbcinst -q -d   # should list [ODBC Driver 18 for SQL Server]
```

The driver loads OpenSSL 1.1 or 3.x. If connections fail with `OpenSSL library could not be loaded`, Homebrew has pointed `$(brew --prefix)/opt/openssl` at OpenSSL 4; point it back at `openssl@3` (Microsoft's documented fix):

```bash
rm "$(brew --prefix)/opt/openssl"
ln -s "$(brew --prefix openssl@3)" "$(brew --prefix)/opt/openssl"
```

For SQL Server command-line access, use your organization’s approved certificate and authentication settings. The application itself does not install, start, or manage SQL Server.

### Switching databases

Change `DB_DIALECT` and the related connection values in `backend/.env`, then restart the backend. The same SQLAlchemy model, repository, service, and route code works for both. You may instead define a complete `DATABASE_URL`, which overrides the individual `DB_*` settings.

Schema changes are managed through Alembic. Run `alembic upgrade head` before starting the backend; `server.sh` runs that command automatically.

## LDAP / Active Directory authentication

Authentication is disabled by default (`LDAP_ENABLED=false`). All directory settings come from `backend/.env`; `backend/.env.example` shows the AGILE domain values.

| Setting | AGILE value | Meaning |
|---|---|---|
| `LDAP_HOST` | DC DNS name (reference IP: `192.168.2.10`) | Must be the name on the DC's certificate for TLS validation; an IP address fails hostname verification |
| `LDAP_PORT` | `389` (StartTLS) or `636` (LDAPS) | |
| `LDAP_BASE_DN` | `DC=agile,DC=local` | Search base for users and groups |
| `LDAP_NETBIOS_DOMAIN` | `AGILE` | Used for `AGILE\user` and NTLM |
| `LDAP_DOMAIN` | `agile.local` | UPN suffix (`user@agile.local`) |
| `LDAP_AUTH_METHOD` | `NTLM` | `SIMPLE` or `NTLM` |
| `LDAP_START_TLS` / `LDAP_USE_SSL` | `true` / `false` | Exactly one secure transport; certificate and hostname are always verified |
| `LDAP_CA_CERT_FILE` | path from IT | CA chain that signed the DC certificate |
| `LDAP_NTLM_SESSION_ENCRYPTION` | `true` | Use NTLM sealing instead of TLS only if the installed ldap3 implements it |
| `LDAP_BIND_DN` / `LDAP_BIND_PASSWORD` | optional | Read-only service account (`AGILE\svc-name` for NTLM, a DN for SIMPLE); empty = search as the signing-in user |
| `LDAP_ALLOWED_GROUPS` | empty | `;`-separated groups allowed to sign in; empty = any authenticated user |
| `LDAP_GROUP_PERMISSIONS` | empty | `Group=perm1,perm2;Other Group=perm3`; unlisted groups grant nothing |
| `LDAP_NESTED_GROUPS`, `LDAP_GROUP_SIZE_LIMIT` | `true`, `500` | Nested-group lookup and its result cap |
| `LDAP_CONNECT_TIMEOUT_SECONDS`, `LDAP_SEARCH_TIMEOUT_SECONDS` | `5`, `5` | Connection, response and search time limits |

### Transport security and NTLM

The application refuses to talk to the directory unless the connection is protected: LDAPS, StartTLS, or NTLM session encryption that the LDAP library actually provides. NTLM authentication itself works over LDAPS/StartTLS. The installed `ldap3` 2.9.1 sets the NTLM "seal" flag but does not encrypt subsequent traffic, so NTLM on plain port 389 is refused ("Secure LDAP must be enabled") rather than sending directory data unencrypted; a future ldap3 that supports `session_security` is detected and used automatically. NTLM also needs MD4, which OpenSSL 3 disables, so `pycryptodome` is a dependency. If IT cannot enable LDAPS/StartTLS with a certificate, that is a security decision to make explicitly, not a configuration flag to flip.

### Authentication flow

1. `POST /api/auth/login` accepts `Administrator`, `AGILE\Administrator` or `administrator@agile.local`; all resolve to the same `sAMAccountName`, and other domains are rejected. Empty passwords are rejected before contacting AD (AD treats them as a successful anonymous bind).
2. The service binds as the user (NTLM `AGILE\user` or SIMPLE `user@agile.local`), or looks the user up with the service account and then binds as the user. Only result code 49 counts as a wrong password; other bind failures (for example a DC requiring signing) return 503.
3. It reads `sAMAccountName`, `userPrincipalName`, `displayName`, `givenName`, `sn`, `mail`, `department`, `title`, `company` and `memberOf`, then resolves direct, nested (`LDAP_MATCHING_RULE_IN_CHAIN`) and primary (`primaryGroupID`, usually Domain Users) groups. Search inputs are escaped; every connection is closed.
4. Authorization is separate: if `LDAP_ALLOWED_GROUPS` is set and the user is in none of them, the response is 403 and no token is issued. Permissions come only from `LDAP_GROUP_PERMISSIONS`; Domain Admins and unknown groups grant nothing unless explicitly mapped.
5. The profile and mapped permissions are created or updated in the `users` table (Unicode preserved; group lists and passwords are never stored), and a short-lived JWT is returned. `GET /api/auth/me` returns the profile and permissions, not group lists.

Logout is client-side (the browser discards its token); a token remains valid until it expires (`ACCESS_TOKEN_EXPIRE_MINUTES`). The backend refuses to start if `JWT_SECRET_KEY` is missing, a placeholder, or shorter than 32 characters; generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. The in-memory login-attempt limit applies per account across username formats; it is a local safeguard, not a distributed rate limiter.

Not decided yet (needs product/IT decisions): which groups may sign in, which permissions each group grants, and whether report endpoints should require authentication or specific permissions. Until configured, any authenticated directory user can sign in and no permissions are granted.

### Live directory checks (company network or VPN required)

The domain controller is on the company's private network. From home, connect to the VPN first; never expose the LDAP service publicly. Then, from `backend/`:

```bash
.venv/bin/python scripts/ldap_live_check.py --probe
```

This sends no credentials. It reports TCP reachability, the DC's `dnsHostName` (use it for `LDAP_HOST`), StartTLS support and the result of validated StartTLS/LDAPS connections. Then make exactly one authentication with an IT-approved, least-privileged test account (not Administrator); the password is prompted without echo and never printed:

```bash
.venv/bin/python scripts/ldap_live_check.py --authenticate
```

It prints the mapped profile, the number of group memberships, and whether `Domain Admins`, `Report Users`, `Scheduler Users` and `docker-users` exist and include the user.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Probe shows ports CLOSED / login takes 5 s then 503 | Not on the company network or VPN |
| `CERTIFICATE_VERIFY_FAILED` | `LDAP_CA_CERT_FILE` missing or wrong CA chain |
| `doesn't match any name` | `LDAP_HOST` is an IP or a name not on the certificate |
| "Secure LDAP must be enabled" | Neither LDAPS nor StartTLS set, and NTLM sealing unavailable |
| "NTLM requires MD4 support" | `pip install -r requirements.txt` (pycryptodome) |
| 503 with correct password | DC requires signing/channel binding, or service account bind failed; check `--authenticate` output |
| 403 after correct password | User is not in `LDAP_ALLOWED_GROUPS` |

Required from IT: the DC's DNS name and whether LDAPS (636) or StartTLS (389) is enabled, the CA certificate chain, an approved least-privileged test account (and optionally a read-only service account), and the group-to-permission policy.

## Run everything

From the project root:

```bash
chmod +x server.sh
./server.sh
```

`server.sh` reclaims ports 8000 and 5173 from existing listener processes before starting, which makes restarting the project with one command reliable. You can choose a different frontend port explicitly with `FRONTEND_PORT=5180 ./server.sh`.

The first run creates a Python virtual environment, installs Python dependencies, and installs frontend packages. Use `Ctrl+C` to stop both development servers; if either server fails to start (for example, a port is already in use), the script stops the other and exits with an error. Both servers listen on `127.0.0.1` only; set `DEV_HOST=0.0.0.0` to expose them deliberately. If another project already serves `localhost:5173` over IPv6, open `http://127.0.0.1:5173` instead.

## Run each side separately

Backend:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## API URLs

- Frontend: `http://localhost:5173`
- API documentation: `http://localhost:8000/docs`
- Health check: `GET http://localhost:8000/health`
- Database connectivity check: `GET http://localhost:8000/health/database`
- List reports: `GET http://localhost:8000/api/reports`
- Create a report: `POST http://localhost:8000/api/reports`
- Login: `POST http://localhost:8000/api/auth/login`
- Current authenticated user: `GET http://localhost:8000/api/auth/me`
- Approved procedures and mapping fields: `GET http://localhost:8000/api/approved-procedures`
- Upload TXT column names: `POST http://localhost:8000/api/uploads/query` (multipart field `file`)
- Create and schedule a one-time job: `POST http://localhost:8000/api/jobs`
- Generated files: `GET http://localhost:8000/api/files` and `GET /api/files/{id}/download`
- Deletion Center: `GET /api/deletion-center` and `DELETE /api/deletion-center` (admin-only; requires typing `DELETE ALL` in the UI)

Example request body:

```json
{ "title": "Quarterly summary", "description": "Example report" }
```

## Development notes

`routes → controllers → services → repositories → models` keeps HTTP concerns, business rules, and database access separate without adding unnecessary layers. The React page uses one centralized `services/api.js` client and the `useReports` hook to call the FastAPI API. CORS origins are configured through `CORS_ORIGINS` in the backend environment file.

### Local job demo

With `AUTH_MODE=mock` in the process environment (for example, `AUTH_MODE=mock ./server.sh`), two local demo identities are available:

| Username | Local password | Access |
| --- | --- | --- |
| `demo_viewer` | `DemoViewer!2026` | Limited: Generated Files (read-only downloads) |
| `demo_admin` | `DemoAdmin!2026` | All configured application menus |

Mock passwords are development-only values in `backend/app/services/mock_auth_service.py`; do not use them in production. The Create Job page uses one form with the five job fields: Job Name, Schedule Date & Time, Company, Email Recipients, and Stored Procedure. Email Recipients are optional; enter an address and press Enter or comma, or paste a comma-separated list. Addresses are trimmed, validated, deduplicated case-insensitively, and stored as a JSON array in the existing `report_jobs.recipients` text column. The limit is configurable with `MAX_EMAIL_RECIPIENTS` (default 10). Removing a chip updates the list; no SMTP delivery is performed. Selecting **Mapped Employee Payroll Report** reveals the TXT upload and mapping section. The **Create & Schedule Job** button creates a one-time job; schedules use Asia/Kolkata and run while the backend is running. The legacy TXT query upload remains available through the separate `/api/uploads/query` endpoint.

The mapping flow accepts either a UTF-8 `.txt` file with one output column name per line or an `.xlsx`/`.xlsm` workbook containing `record type` and `column name` columns. A ready-to-upload example is `samples/mapped_payroll_columns.xlsx`. Excel uploads retain the H/D/T record type and the New Job form displays a four-column mapping table: Column Name, Record Type, DB Column Name, and Format (Text, TextPhone, or Date). Record Type can be adjusted with its H/D/T dropdown. The form also provides a Select Delimiter dropdown (Comma, Pipe, Semicolon, or Tab); comma is the default for new and legacy jobs. Map every extracted name to an approved database field using the searchable selectors, choose formats as needed, create a future job, wait for the scheduler, then inspect `/api/runs` and `/api/files`. The backend persists the ordered names, delimiter, and mapping JSON on the job and passes both `@company_id` and `@column_mappings` to SQL Server's `dbo.usp_GenerateMappedPayrollReport`. Legacy `display_name`/`database_field` mappings remain compatible; uploaded files are never executed as SQL.

### Admin dashboard

After signing in, the React application presents only the authorized areas in a responsive sidebar. LDAP/Active Directory authorization uses `backend/app/config/menu.yaml`, while local mock authentication uses `backend/app/config/mock_menu.yaml`. Each menu has an id, label, path, and groups; LDAP group claims (including full `CN=...,DC=...` distinguished names) are normalized and compared case-insensitively. The policy may grant Dashboard, Jobs, Generated Files, and Deletion Center. Dashboard is not shown in the navigation, and users with Jobs access review and download generated files from Job Details instead of a separate Generated Files menu; users without Jobs access (such as viewers) see Generated Files so they can still download reports. Only menus whose configured group matches the authentication response are returned. The API returns both menu ids and display metadata from `/api/auth/menus`; backend route guards use the ids in the signed token, so hiding a menu does not replace server-side authorization. Jobs is a unified screen for creating, scheduling, monitoring, and reviewing execution history. Dashboard metrics and tables are loaded from the FastAPI workflow endpoints; no dashboard counts are hard-coded. Tables support horizontal scrolling on small screens, and the sidebar collapses to an icon rail on mobile.
The admin-only Deletion Center removes application-created report jobs, their execution runs, generated-file metadata/files, and associated uploaded column-list files. It never removes companies, employees, payroll data, users, permissions, or configuration. The UI shows a count preview and requires typing `DELETE ALL` plus a confirmation prompt. Inside Deletion Center, the temporary **Generated Files** tab lists reports across all jobs with generation time, file size, row count, and download actions; the **Delete Jobs & Files** tab retains the cleanup controls. The file list reloads whenever its tab is opened.

## Local workflow demonstration

For the home demonstration, set `AUTH_MODE=mock` in local `backend/.env` (never in production), then sign in with either documented mock account. Menu-to-group mappings are maintained in the two mode-specific YAML files above. After SQL Server migrations are applied, the app idempotently seeds Companies A–C, fictional employees, and three payroll months. The Jobs screen opens the existing one-form job creator in a drawer and combines scheduled jobs, status filters, run/enable actions, details, and execution history. The approved procedure registry exposes Mapped Employee Payroll Report plus Employee Payroll Report, Monthly Payroll Summary, Department-wise Payroll Report, Employee Salary Breakdown, and Company Payroll Report. The mapping-aware procedure is the only procedure advertised with dynamic field selection; the separate legacy TXT upload path still accepts only the documented read-only payroll query. Generated payroll CSVs are stored in `generated_reports/`; email delivery is intentionally not implemented. Error logs are stored in `logs/frontend`, `logs/backend`, and `logs/jobs` by default. Set `LOG_DIR` in `backend/.env` to move the complete log folder, for example `LOG_DIR=/var/log/generate-report`. Schedules use Asia/Kolkata and run only while the application is running. All demo identities and payroll values are fictional.

## Local tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests
```

By default these use in-memory SQLite, an in-memory fake Active Directory (accounts, nested and primary groups) and local TLS sockets to validate routing, validation, authentication and JWT handling. They do not prove connectivity to a real SQL Server or Active Directory.

With the configured SQL Server reachable and migrations applied, also run the live SQL Server integration tests. They use the configured database, tag their rows with a unique `itest-` prefix, and delete only those rows:

```bash
cd backend
RUN_SQLSERVER_TESTS=1 .venv/bin/python -m unittest discover -s tests
```

### Client and email selections

The New Job form uses the existing `companies` list as the Client list because Company and Client are the same business entity. Multiple companies/clients can be selected with a searchable chip selector; each selected company ID has its own email-ID selector. The saved `client_selections` JSON maps real company IDs to selected email IDs; legacy `recipients` values remain supported.

Export Split By supports File Name, Client ID, Pay Date, and combination choices such as File Name + Client ID, File Name + Pay Date, Client ID + Pay Date, and all three. Client ID uses the selected company's real `companies.id` and the `employees.company_id → payroll.employee_id` relationship. Pay Date uses the employee-level `employees.paydate` field; company/date combinations produce separate CSV members. Payroll-period data remains available through the `payroll_month` mapping field. Split runs create separate delimiter-aware CSV members and expose them as one downloadable ZIP. The original approved company procedure remains unchanged.

Mapped Excel configurations may assign columns to H (Header), D (Detail), or T (Trailer). The application emits those records in H → D → T order and derives trailer employee counts and net salary totals from the actual detail rows. Existing all-detail mappings retain the prior CSV header-row behavior.

The New Job wizard offers Daily, Weekly, and Monthly schedules. The API still accepts the legacy One Time, Every 2 Minutes, and Every 1/2/4 Hours types for existing jobs; opening such a job in the editor normalizes it to Daily. Execution Date and Time (Asia/Kolkata) must be in the future and are the first eligible run for every schedule type. Weekly uses the selected weekday (Sunday–Saturday) and Monthly uses the selected day of month, falling back to the month's last day. Recurring schedules use APScheduler cron/interval triggers, coalesced missed runs, and a five-minute misfire grace period. A job runs at most once at a time: a manual or scheduled run requested while the same job is executing is rejected.

Filters and Export Split By options other than File Name require an uploaded column list (Mapped Employee Payroll Report). Text conditions (contains, starts with, ends with, does not contain) apply only to text fields. All-detail layouts always include a header row; H/D/T layouts write header, detail, and trailer records. "File Name + …" split options group like their counterparts and prefix each CSV member with the job's file name.
