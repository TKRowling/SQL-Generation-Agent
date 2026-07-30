# AskMe Web - PostgreSQL Edition

AskMe Web is a React and FastAPI replacement for the original Telegram text-to-SQL assistant. This edition runs directly with Python and Node.js and connects to local or remote PostgreSQL. Docker is not required or included.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Pydantic, Pydantic Settings
- AI: Ollama REST API without an API key
- Database: PostgreSQL through `psycopg` and `psycopg-pool`
- SQL AST: SQLGlot with the PostgreSQL dialect
- Runtime skill: `backend/app/skills/askme-data-assistant/SKILL.md`

## Current workflow

1. Route forbidden mutations, metadata explanations, normal conversation, and SELECT-only data questions separately.
2. Build a cached catalog and remove restricted tables and columns.
3. Semantically rank approved tables using identifiers, columns, business synonyms, and foreign-key neighbors.
4. Generate exactly one PostgreSQL `SELECT`.
5. Parse and authorize the SQL AST against the selected schema and authoritative catalog.
6. Run PostgreSQL `EXPLAIN (FORMAT JSON)` and reject excessive estimated cost or rows.
7. Correct eligible policy, plan, execution, or result-verification failures within a bounded loop.
8. Execute only validated SQL in a read-only PostgreSQL session with time and row limits.
9. Verify deterministic result invariants and summarize only authoritative rows.
9. Add deterministic insights and a useful line, bar, or pie/donut chart when appropriate.
10. Record an audit event and return the report, formatted copyable SQL, and exports.
11. Keep bounded backend context and multiple browser conversations.

AskMe's two database capabilities are:

- General metadata answers grounded in approved database/schema/table/column metadata,
  with official comments preferred and AI inference clearly qualified.
- SELECT-only SQL generation protected by catalog validation, read-only execution,
  bounded correction, limits, and audit logging.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component and trust-boundary details.

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19 or newer
- A running PostgreSQL server
- A PostgreSQL database and login role
- Ollama installed locally or reachable over the network

## 1. Configure a local PostgreSQL connection

Copy the environment template:

```powershell
Copy-Item backend\.env.example backend\.env
```

For a typical local PostgreSQL installation, edit `backend/.env` as follows:

```env
DB_URL=postgresql://localhost:5432/askme
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_SCHEMA=core_banking
DB_SCHEMAS=accounts,audit_compliance,cards,core_banking,customer360,deposits,digital_banking,fraud_risk,loans,payments
```

`DB_SCHEMA` is the default. `DB_SCHEMAS` is the comma-separated allowlist shown in the user selector. To add or remove a schema later, edit only this line and restart FastAPI; no Python or React change is required. `public` is intentionally excluded from this example. The application also accepts credentials inside the URL:

```env
DB_URL=postgresql://postgres:encoded_password@localhost:5432/askme
DB_USER=
DB_PASSWORD=
DB_SCHEMA=public
```

Accepted URL formats:

```text
postgresql://localhost:5432/askme
postgres://localhost:5432/askme
jdbc:postgresql://localhost:5432/askme
```

For local connections that explicitly disable TLS:

```env
DB_URL=postgresql://localhost:5432/askme?sslmode=disable
```

Configure the Ollama provider in the same file:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TEMPERATURE=0.1
OLLAMA_TIMEOUT_SECONDS=120
```

Useful database settings:

```env
DB_POOL_SIZE=5
DB_CONNECT_TIMEOUT_SECONDS=10
DB_STATEMENT_TIMEOUT_MS=30000
DB_EXPLAIN_MAX_COST=100000
DB_EXPLAIN_MAX_ROWS=1000000
DB_EXPLAIN_MAX_JOINS=8
MAX_ROWS=50
SCHEMA_MAX_TABLES=8
SQL_MAX_ATTEMPTS=3
EXPOSE_SQL=false
```

## 2. Test PostgreSQL

Confirm that PostgreSQL is running and the database exists. From a terminal with PostgreSQL tools installed:

```bash
psql -h localhost -p 5432 -U postgres -d askme
```

Then test through the FastAPI project:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m app.scripts.dbping
```

## 3. Start the backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation:

```text
http://localhost:8000/docs
```

## 4. Start the frontend

Open another terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

During development, Vite proxies `/api` to `http://localhost:8000`.

## One-command development startup

After dependencies and environment files are prepared:

```powershell
.\run-dev.ps1
```

On macOS or Linux:

```bash
chmod +x run-dev.sh
./run-dev.sh
```

## Read-only PostgreSQL role

Using a separate read-only role is safer than connecting as `postgres`. Run the following as an administrator and replace the database, schema, role, and password values:

```sql
CREATE ROLE askme_reader LOGIN PASSWORD 'replace_this_password';
GRANT CONNECT ON DATABASE askme TO askme_reader;
GRANT USAGE ON SCHEMA public TO askme_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO askme_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO askme_reader;
```

Then configure:

```env
DB_URL=postgresql://localhost:5432/askme
DB_USER=askme_reader
DB_PASSWORD=replace_this_password
DB_SCHEMA=public
```

The backend additionally sets `default_transaction_read_only=on`, but PostgreSQL role permissions remain the primary security boundary.

## Direct CLI query

With the backend virtual environment active:

```bash
python -m app.scripts.ask "how many documents were created in the last 7 days"
```

## Tests

Current verification baseline: 56 backend tests pass, the frontend production build passes, and the runtime skill validates.

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Show configuration-level health information |
| `POST` | `/api/chat` | Normal chat or automatic database routing |
| `POST` | `/api/chat/reset` | Clear one browser session's backend memory |
| `PUT` | `/api/chat/history` | Restore the valid conversation prefix after editing a question |
| `GET` | `/api/db/ping` | Test the PostgreSQL connection |
| `GET` | `/api/db/tables?schema=finance` | List tables in one approved selected schema |
| `POST` | `/api/schema/refresh?schema=finance` | Refresh one approved schema catalog |

## Runtime skill

The SQL-generation and summarization rules are loaded at runtime from:

```text
backend/app/skills/askme-data-assistant/SKILL.md
```

Keep these markers unchanged when editing the skill:

```text
<!-- SQL_RULES_START -->
<!-- SQL_RULES_END -->
<!-- SUMMARY_RULES_START -->
<!-- SUMMARY_RULES_END -->
```

## Project documentation

- [Current architecture](ARCHITECTURE.md)
- [Project overview](PROJECT_OVERVIEW.md)
- [How to build the SQL agent](HOW_TO_BUILD_SQL_AGENT.md)

## Security notes

- Prefer a dedicated role with only `CONNECT`, schema `USAGE`, and table `SELECT` permissions.
- Keep database credentials and any optional external-provider credentials only in `backend/.env`.
- Keep `EXPOSE_SQL=false` outside developer debugging.
- The backend adds a row cap, a read-only session setting, and a query timeout.
- Application checks cannot make a highly privileged PostgreSQL role safe.
- Use SSO or an identity-aware proxy when exposing the API beyond a trusted local network.
