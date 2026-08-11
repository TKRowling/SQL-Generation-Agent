# AskMe Web - PostgreSQL Edition

AskMe Web is a React and FastAPI replacement for the original Telegram text-to-SQL assistant. This edition runs directly with Python and Node.js and connects to local or remote PostgreSQL. Docker is not required or included.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Pydantic, Pydantic Settings
- Agent orchestration: LangGraph with LangChain tools
- AI: selectable Cloudflare Workers AI or Ollama REST API
- Database: PostgreSQL through `psycopg` and `psycopg-pool`
- SQL AST: SQLGlot with the PostgreSQL dialect
- Runtime skill: `backend/app/skills/askme-data-assistant/SKILL.md`

## Current workflow

1. Block mutation intent before agent execution.
2. Use the LangGraph supervisor to route metadata, SQL, and general-chat requests.
3. Let the schema agent build a governed catalog with restricted metadata removed.
4. Semantically rank approved tables using identifiers, columns, business synonyms, and foreign-key neighbors.
5. Let the SQL agent reuse a schema-versioned plan or propose one `SELECT`.
6. Call explicit LangChain tools for AST validation, EXPLAIN, read-only execution, and result verification.
7. Route eligible failures through the bounded correction agent.
8. Let the reporting agent summarize only authoritative rows and propose validated charts.
9. Record an audit event and return the report, formatted copyable SQL, and exports.
10. Keep bounded backend context and multiple browser conversations.

AskMe's two database capabilities are:

- General metadata answers grounded in approved database/schema/table/column metadata,
  with official comments preferred and AI inference clearly qualified.
- SELECT-only SQL generation protected by catalog validation, read-only execution,
  bounded correction, limits, and audit logging.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component and trust-boundary details.

The deployed agent inventory is available from `GET /api/agent/info` for demonstrations and operational verification.

For safe local graph tracing, set `AGENT_DEBUG=true` in `backend/.env` and restart FastAPI. See [backend/app/agents/README.md](backend/app/agents/README.md) for the simplified folder map and debugging workflow.

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19 or newer
- A running PostgreSQL server
- A PostgreSQL database and login role
- Either Cloudflare Workers AI credentials or a reachable Ollama service

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

Choose the AI provider in the same file. For Cloudflare Workers AI:

```env
AI_PROVIDER=cloudflare
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token
CF_AI_MODEL=@cf/meta/llama-3.1-8b-instruct-fast
CF_SQL_MODEL=@cf/meta/llama-3.1-8b-instruct-fast
CF_KNOWLEDGE_MODEL=@cf/meta/llama-3.1-8b-instruct-fast
CF_AI_TEMPERATURE=0.1
CF_AI_TIMEOUT_SECONDS=60
```

The SQL model handles SELECT planning and bounded correction. The knowledge model handles database metadata explanations, verified-result summaries, chart planning, and general database questions. A blank specialized setting falls back to `CF_AI_MODEL`.

For a customer-managed Ollama service:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_SQL_MODEL=qwen2.5-coder:14b
OLLAMA_KNOWLEDGE_MODEL=llama3.1:8b
OLLAMA_AI_TEMPERATURE=0.1
OLLAMA_AI_TIMEOUT_SECONDS=120
```

Blank specialized Ollama model settings fall back to `OLLAMA_MODEL`. If FastAPI and Ollama run in separate containers on the same Docker network, use the Ollama service URL such as `http://ollama:11434`. Restart FastAPI after changing `AI_PROVIDER`, because the provider clients are created during application import.

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
PLAN_CACHE_PATH=logs/plan_cache.sqlite3
PLAN_CACHE_MAX_ENTRIES=1000
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

Current verification baseline: 61 backend tests pass, the frontend production build passes, and the runtime skill validates.

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
