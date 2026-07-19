# AskMe Web — PostgreSQL Edition

AskMe Web is a React and FastAPI replacement for the original Telegram text-to-SQL assistant. This edition runs directly with Python and Node.js and connects to local or remote PostgreSQL. Docker is not required or included.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Pydantic, Pydantic Settings
- AI: Cloudflare Workers AI REST API
- Database: PostgreSQL through `psycopg` and `psycopg-pool`
- Runtime skill: `backend/app/skills/askme-data-assistant/SKILL.md`

## Preserved workflow

1. Inspect the selected PostgreSQL schema through `information_schema`.
2. Hide secret columns such as `password` and `key_secret` from the model.
3. Cache a compact schema summary for 10 minutes by default.
4. Route normal conversation separately from database questions.
5. Generate exactly one PostgreSQL `SELECT` statement.
6. Reject non-SELECT statements, multiple statements, mutation keywords, and secret-column references.
7. Open database sessions as read-only and apply a statement timeout.
8. Add a hard result limit when the SQL does not contain one.
9. Retry SQL generation once after a normal PostgreSQL query error.
10. Summarize only rows actually returned by PostgreSQL.
11. Keep the last eight user/assistant turns per browser session in process memory.

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19 or newer
- A running PostgreSQL server
- A PostgreSQL database and login role
- Cloudflare account ID and Workers AI API token

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
DB_SCHEMA=public
```

Replace `askme` with your actual database name. The application also accepts credentials inside the URL:

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

Complete the Cloudflare values in the same file:

```env
CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token
CF_AI_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
CF_AI_TEMPERATURE=0.1
```

Useful database settings:

```env
DB_POOL_SIZE=5
DB_CONNECT_TIMEOUT_SECONDS=10
DB_STATEMENT_TIMEOUT_MS=30000
MAX_ROWS=50
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
| `GET` | `/api/db/ping` | Test the PostgreSQL connection |
| `GET` | `/api/db/tables` | List tables in `DB_SCHEMA` |
| `POST` | `/api/schema/refresh` | Refresh the cached schema summary |

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

## Security notes

- Prefer a dedicated role with only `CONNECT`, schema `USAGE`, and table `SELECT` permissions.
- Keep database and Cloudflare credentials only in `backend/.env`.
- Keep `EXPOSE_SQL=false` outside developer debugging.
- The backend adds a row cap, a read-only session setting, and a query timeout.
- Application checks cannot make a highly privileged PostgreSQL role safe.
- Use SSO or an identity-aware proxy when exposing the API beyond a trusted local network.
