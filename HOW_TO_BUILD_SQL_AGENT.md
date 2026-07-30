# How to Build the AskMe SQL Agent

For the latest implementation-level architecture and trust boundaries, see [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Purpose

This guide explains how the team can build and maintain AskMe: a secure, read-only SQL Agent that converts a business question into validated PostgreSQL SQL and returns an understandable report.

The current implementation uses:

- React and TypeScript
- FastAPI and Pydantic
- PostgreSQL and Psycopg
- Ollama local AI service without an API key
- `llama3.1:8b` (default pilot model)
- Optional Cloudflare Workers AI provider

Docker, Kubernetes, LangGraph, and a true multi-agent graph are not required for the current local pilot.

## 2. Target result

A user asks:

```text
Show monthly transaction count and total transaction amount for the latest six months.
```

AskMe returns:

- A business-friendly answer
- Executive insights
- A line, bar, or interpretation-aware pie chart
- Database result rows
- Formatted SQL
- CSV, Excel, and PDF exports
- Request ID and execution time
- An audit event

## 3. Main flow

```text
User question
  → React frontend
  → POST /api/chat
  → Deterministic metadata/data router
  → Semantic retrieval from the approved schema catalog
  → Configured AI provider plans and generates one SELECT
  → SQLGlot AST policy checker
  → PostgreSQL EXPLAIN cost guard
  → Read-only PostgreSQL execution
  → Deterministic result verification
  → Grounded AI business summary
  → Validated insights and chart
  → Audit event is recorded
  → React displays the report
```

## 4. Project structure

```text
AskMe-Web/
├── backend/
│   ├── app/
│   │   ├── api/routes/       FastAPI endpoints
│   │   ├── core/             Configuration, security, errors
│   │   ├── models/           Request and response models
│   │   ├── services/         Agent, AI, database, schema, audit, reports
│   │   └── skills/           Runtime SQL Agent instructions
│   └── tests/                Backend automated tests
├── frontend/
│   ├── src/api/              FastAPI client
│   ├── src/components/       Chat, table, chart, sidebar, SQL UI
│   ├── src/utils/            Sessions and browser storage
│   └── src/types/            API TypeScript contracts
└── *.md                      Project and team documentation
```

## 5. Build sequence

### Step 1 — Configure the environment

Create `backend/.env` from `backend/.env.example`.

Configure:

```env
DB_URL=postgresql://localhost:5432/banking_demo
DB_USER=your_read_only_user
DB_PASSWORD=your_password
DB_SCHEMA=core_banking
DB_SCHEMAS=accounts,audit_compliance,cards,core_banking,customer360,deposits,digital_banking,fraud_risk,loans,payments

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TEMPERATURE=0.1
OLLAMA_TIMEOUT_SECONDS=120

EXPOSE_SQL=true
MAX_ROWS=50
DB_STATEMENT_TIMEOUT_MS=30000
DB_EXPLAIN_MAX_COST=100000
DB_EXPLAIN_MAX_ROWS=1000000
DB_EXPLAIN_MAX_JOINS=8
SCHEMA_MAX_TABLES=8
SQL_MAX_ATTEMPTS=3
```

Never commit real credentials.

### Step 2 — Build database connectivity

Implement a PostgreSQL connection pool that:

- Uses a dedicated read-only database role
- Sets the approved schema search path
- Enables read-only transaction behavior
- Applies connection and statement timeouts
- Converts database values into JSON-safe values

Primary file:

```text
backend/app/services/database.py
```

Verify through:

```http
GET /api/db/ping
```

Expected result:

```json
{
  "reachable": true,
  "database": "banking_demo",
  "schema": "core_banking",
  "schemas": ["accounts", "core_banking", "customer360", "loans"],
  "tables": 30
}
```

### Step 3 — Build schema discovery

Query PostgreSQL metadata for:

- Tables
- Columns and data types
- Primary keys
- Unique keys
- Foreign-key relationships

Remove restricted tables and columns before producing the model-visible schema.

Primary file:

```text
backend/app/services/schema.py
```

Supporting endpoints:

```http
GET  /api/db/tables
POST /api/schema/refresh
```

### Step 4 — Create the runtime skill

Define the model’s SQL and summarization behavior in:

```text
backend/app/skills/askme-data-assistant/SKILL.md
```

The SQL rules must require:

- Exactly one PostgreSQL `SELECT`
- Only supplied tables and columns
- Exact use of explicitly requested real tables
- Explicit join conditions
- No credential or restricted columns
- No mutation SQL
- No invented identifiers or values
- Appropriate grouping, ordering, and limits

The summary rules must require:

- Use only returned rows
- No invented totals, dates, names, or statuses
- Correct handling of empty and capped results
- No destructive SQL suggestions

### Step 5 — Integrate the model

Create a provider-based AI client that sends:

- Runtime skill instructions
- Approved table inventory and progressively selected relevant schemas
- Bounded conversation history
- User question

Primary file:

```text
backend/app/services/ai.py
```

Ollama receives `POST /api/chat` with `stream: false` and returns the assistant text in `message.content`. No `Authorization` header or API key is required. Cloudflare can remain as an explicitly selected alternative. The model never receives database credentials and cannot execute SQL directly.

### Step 6 — Build the query-agent workflow

The main agent is:

```text
backend/app/services/query_agent.py
```

Implement this bounded process:

```text
1. Route metadata explanations and data questions deterministically
2. Retrieve relevant tables from the selected approved schema
3. Generate one SELECT
4. Parse and validate the PostgreSQL AST
5. Reject excessive EXPLAIN cost, rows, or joins
6. Execute through a read-only transaction
7. Verify result invariants
8. Correct eligible failures within `SQL_MAX_ATTEMPTS`
9. Summarize only authoritative rows
10. Validate reporting and return the response
```

This is one staged agent with a configurable, bounded correction loop. The default allows three total attempts and cannot run indefinitely.

### Step 7 — Add deterministic routing

Do not use AI for everything.

Handle these directly:

- Database name requests
- Table-list requests
- Destructive or mutating requests

Example:

```text
“List all tables”
→ query PostgreSQL metadata directly
→ no AI-provider call
```

```text
“Delete the accounts table”
→ return refusal immediately
→ no AI-provider call
→ no PostgreSQL query
```

### Step 8 — Validate SQL independently

Model instructions are not a security boundary.

Before execution, verify with `backend/app/services/query_checker.py`:

- Exactly one PostgreSQL `SELECT` exists.
- CTEs and subqueries remain read-only.
- Every physical schema, table, alias, and qualified column is approved.
- Restricted identifiers and wildcard projections are rejected.
- Join count and row limits remain bounded.

Primary files:

```text
backend/app/services/database.py
backend/app/services/query_checker.py
backend/app/services/cost_guard.py
backend/app/services/result_verifier.py
```

Run `EXPLAIN (FORMAT JSON)` without `ANALYZE` before business-data execution. Reject plans above the configured estimated cost or estimated row thresholds. After execution, verify count, top-N, ordering, limit, and chart-shape invariants before asking the model to summarize.

### Step 9 — Build the chat endpoint

Primary endpoint:

```http
POST /api/chat
```

Primary file:

```text
backend/app/api/routes/chat.py
```

Request:

```json
{
  "session_id": "conversation-uuid",
  "message": "Show total transaction amount by transaction type.",
  "force_data": false,
  "schema": "payments"
}
```

Response:

```json
{
  "kind": "data",
  "answer": "Deposits have the highest total transaction amount.",
  "rows": [
    {
      "transaction_type": "DEPOSIT",
      "total_transaction_amount": 910000
    }
  ],
  "row_count": 1,
  "sql": "SELECT ...",
  "insights": [
    "The query returned 1 row."
  ],
  "chart": null,
  "request_id": "request-uuid",
  "execution_ms": 2500
}
```

### Step 10 — Add conversation context

Store recent user and assistant messages by `session_id`.

Primary file:

```text
backend/app/services/history.py
```

Reset endpoint:

```http
POST /api/chat/reset
```

Keep history bounded to control token usage.

For stable 8B-model behavior:

- Send history to SQL generation only for clear follow-up questions.
- Do not pass previous failed turns into a new standalone question.
- Recheck `UNSUPPORTED` claims against the complete approved catalog.
- Cache successful plans by normalized question and schema.
- Revalidate cached plans through every deterministic guard before execution.

### Step 11 — Build analysis and chart selection

Analyze returned rows deterministically for:

- Row count
- Numeric minimum and maximum
- Categorical chart shape
- Date/time-series chart shape

For chart-worthy questions, the LLM may propose only the chart type, title, and exact
returned column names. Validate those axes against the authoritative rows and fall back
to deterministic selection if the planner is unavailable or invalid. Never allow the
LLM to generate or modify chart values.

Primary file:

```text
backend/app/services/reporting.py
```

Return a chart specification rather than an image:

```json
{
  "type": "line",
  "title": "Transaction Count by Month",
  "x_key": "transaction_month",
  "y_keys": ["transaction_count"]
}
```

### Step 12 — Add audit logging

Record:

- UTC timestamp
- Request ID
- Session ID
- User question
- Routing decision
- Status
- Generated SQL
- Row count
- Execution time

Primary file:

```text
backend/app/services/audit.py
```

Pilot output:

```text
backend/logs/audit.jsonl
```

Production improvement: move audit events to protected centralized storage and include authenticated user identity.

### Step 13 — Build the reporting frontend

The frontend should render:

- User and assistant messages
- Database and row-count badges
- Executive insights
- Bar, line, and pie charts selected for the appropriate interpretation
- Scrollable data table
- Formatted SQL block
- Copy SQL control
- CSV, Excel, and PDF controls
- Request ID and execution time
- Current conversation and active-schema context
- Clear loading, empty-result, and error states

Important files:

```text
frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/components/MessageCard.tsx
frontend/src/components/DataTable.tsx
frontend/src/components/ReportInsights.tsx
frontend/src/styles.css
```

### Step 14 — Add conversation history UI

Store multiple browser conversations with:

- Unique conversation IDs
- Title generated from the first question with inline rename support
- Collapsible desktop sidebar and mobile history drawer
- One backend-approved schema selection per conversation
- Editable user questions that truncate obsolete later turns and regenerate the answer
- Created and updated timestamps
- Messages
- Active conversation state
- Active schema indicator in both the workspace header and composer

Important files:

```text
frontend/src/components/Sidebar.tsx
frontend/src/utils/storage.ts
frontend/src/utils/session.ts
```

Each frontend conversation ID is also used as the backend `session_id`.

### Step 15 — Test every layer

Backend tests should cover:

- Environment parsing
- Database URL parsing
- SQL safety
- Restricted identifiers
- Schema filtering
- Intent routing
- Metadata routing
- Runtime skill loading
- API responses

Run:

```bat
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend verification:

```bat
cd frontend
npm.cmd run build
```

Current evidence:

```text
57 backend tests passed
Frontend production build passed
Runtime skill validation passed
```

## 6. Endpoint summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Check backend and configuration |
| `GET` | `/api/db/ping` | Check PostgreSQL connection |
| `GET` | `/api/db/tables` | List approved tables |
| `POST` | `/api/schema/refresh` | Refresh schema metadata |
| `POST` | `/api/chat` | Run the complete SQL Agent flow |
| `POST` | `/api/chat/reset` | Clear one conversation context |

## 7. Security checklist

Before accepting a card as Done, confirm:

- [ ] Database role is read-only.
- [ ] Only approved schemas are configured.
- [ ] Restricted tables are hidden and blocked.
- [ ] Restricted columns are hidden and blocked.
- [ ] Only one `SELECT` can execute.
- [ ] Row cap is enforced.
- [ ] Statement timeout is enforced.
- [ ] Model never receives credentials.
- [ ] User input and generated SQL are audited.
- [ ] Security tests pass.

## 8. Team responsibilities

| Role | Responsibility |
|---|---|
| Product Owner | Define use cases, scope, and success metrics |
| Business Analyst | Define questions, KPIs, and expected answers |
| Data Engineer | Maintain schema metadata and business definitions |
| DBA | Create read-only role and tune database access |
| Backend Engineer | Build API, validation, execution, and audit services |
| AI Engineer | Maintain prompts, skill, model integration, and evaluation |
| Frontend Engineer | Build chat, charts, tables, history, and exports |
| Security | Approve access policy, PII restrictions, and threat tests |
| QA | Maintain golden questions and regression tests |

## 9. Recommended next work

Prioritize these production improvements:

1. Golden business-question dataset
2. Security red-team test suite
3. Governed function allowlist and deeper AST lineage checks
4. SSO and role-based authorization
5. Central audit storage
6. Persistent shared conversation storage
7. Governed business glossary and KPI catalog
8. Governed vector and business-glossary retrieval
9. LangGraph orchestration after stage contracts are stable

## 10. Card completion template

Use this template when updating the team:

```text
Card:
Owner:
Status:
Implemented:
Acceptance criteria:
Test evidence:
Known limitations:
Next dependency:
```

## 11. Short explanation for the team

> Build the SQL Agent as a controlled pipeline, not as an unrestricted chatbot. Let the model understand the question and propose SQL, but keep schema access, security validation, database execution, limits, reporting, and audit logging under deterministic application control. The model should never receive credentials or execute SQL directly.
