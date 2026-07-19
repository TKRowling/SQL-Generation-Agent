# AskMe — AI Query & Reporting Agent

## 1. Project overview

AskMe is a secure, read-only AI query and reporting application for PostgreSQL. It allows a business user to ask questions in plain language, converts supported questions into PostgreSQL `SELECT` statements, validates and executes those statements through a read-only connection, and returns a business-friendly answer with result tables, insights, charts, exports, and formatted SQL.

The current pilot is configured for the `ai_query_test` database and the `ai_demo` schema. The architecture is reusable for other approved PostgreSQL schemas through environment configuration.

AskMe is designed to reduce the number of routine ad-hoc requests handled manually by data analysts while preserving strict database safety controls.

## 2. Business objective

AskMe helps business users answer questions such as:

- How many bank transactions were processed this month?
- What is the total transaction amount by transaction type?
- Which branches have the highest transaction volume?
- How has transaction activity changed over the latest six months?
- What are the latest balances for customer accounts?

The target user does not need to know table names, joins, SQL syntax, aggregation rules, or database-specific date functions.

## 3. Current capabilities

### Natural-language database queries

- Accepts business questions through a chat interface.
- Detects database-related questions and general conversation.
- Supplies the approved database schema to the language model.
- Generates one PostgreSQL `SELECT` statement.
- Retries once when generated SQL fails for a correctable reason.
- Retains bounded conversational context for follow-up questions.

### Deterministic metadata requests

Common metadata requests bypass the language model:

- “What is the name of the database?”
- “List all tables in the current schema.”

This improves correctness, reduces latency, and avoids unnecessary AI usage.

### Reporting

- Natural-language answer based on returned rows.
- Executive insight panel.
- Automatic bar or line chart recommendation based on result shape.
- Scrollable result table.
- CSV export.
- Excel-compatible `.xls` export.
- Browser print-to-PDF report.
- Formatted, syntax-highlighted, copyable SQL.
- Request ID and execution-time trace.

### Conversation history

- Multiple locally stored conversations.
- Automatic title based on the first user question.
- Conversation switching and deletion.
- Separate backend session context per conversation.
- Up to 30 conversations and 100 messages per conversation in browser storage.
- Migration of the original single-conversation browser history.

## 4. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend API | FastAPI, Pydantic |
| Database | PostgreSQL through Psycopg 3 connection pooling |
| AI provider | Cloudflare Workers AI REST API |
| Default model | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| HTTP client | HTTPX |
| Backend tests | Pytest, pytest-asyncio |
| Browser persistence | `localStorage` |
| Audit persistence | Append-only JSON Lines file |

The current implementation does not require Docker or Kubernetes.

## 5. Architecture

```text
┌──────────────────────────────┐
│ React reporting interface    │
│ Chat · History · Charts      │
│ Tables · SQL · Exports       │
└──────────────┬───────────────┘
               │ HTTP / JSON
               ▼
┌──────────────────────────────┐
│ FastAPI application          │
│ Authentication · Routing     │
│ Error mapping · Audit        │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Query-agent pipeline         │
│ Intent → Metadata → Schema   │
│ SQL → Policy → Execution     │
│ Summary → Insights → Chart   │
└───────┬──────────────┬───────┘
        │              │
        ▼              ▼
┌───────────────┐  ┌───────────────┐
│ Cloudflare AI │  │ PostgreSQL    │
│ SQL + summary │  │ Read-only     │
└───────────────┘  └───────────────┘
```

## 6. End-to-end workflow

### Step 1: Receive and authenticate the request

The frontend sends a `POST /api/chat` request containing:

- A unique conversation/session ID.
- The user’s message.
- Whether database-only routing is enabled.

When `ASKME_API_KEY` is configured, the backend requires the matching value in the `X-API-Key` header.

### Step 2: Apply intent-level safety rules

Before calling the model or database, the API blocks requests containing mutation intent such as:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `CREATE`
- `TRUNCATE`
- privilege or execution commands

A blocked request produces no AI call, no database call, no rows, and no destructive SQL example.

### Step 3: Resolve deterministic metadata

Database-name and table-list questions are answered directly from configuration or PostgreSQL metadata. These questions do not need model inference.

### Step 4: Discover the approved schema

The schema service reads:

- Table names.
- Column names and simplified types.
- Primary keys.
- Unique keys.
- Foreign-key relationships.

Restricted tables and columns are removed before the schema is provided to the language model. Schema results are cached for `SCHEMA_CACHE_SECONDS` and may be refreshed through the API.

### Step 5: Route the request

The query agent decides whether the message is:

- A database question requiring SQL.
- A general conversation that does not require SQL.
- A metadata request already handled deterministically.
- A forbidden mutation already blocked by the API.

### Step 6: Generate SQL

For a database question, Cloudflare Workers AI receives:

- The SQL-generation rules from the runtime skill.
- The filtered PostgreSQL schema summary.
- Bounded conversation history.
- The current question.

The model must return exactly one executable PostgreSQL `SELECT` statement.

### Step 7: Validate SQL

The backend independently enforces:

- The statement must begin with `SELECT`.
- Only one statement is allowed.
- Mutation and administration keywords are forbidden.
- Restricted table and column identifiers are forbidden.
- Credential columns are forbidden.
- A hard result limit is appended when the query has no limit.

Model instructions are not treated as a security boundary. Validation and database permissions provide defense in depth.

### Step 8: Execute through PostgreSQL

The database service uses a connection pool configured with:

- Read-only transaction behavior.
- An approved schema search path.
- Connection timeout.
- Statement timeout.
- Maximum result-row cap.

The production database role should independently have only `CONNECT`, schema `USAGE`, and approved `SELECT` privileges.

### Step 9: Recover from a correctable SQL error

If PostgreSQL rejects generated SQL for a non-connectivity reason, the agent sends the database error back to the SQL-generation stage and requests one corrected `SELECT`. Connectivity errors are not incorrectly treated as SQL-generation mistakes.

### Step 10: Summarize results

The model receives only the question, executed SQL, row-count context, and returned data. The runtime skill requires the answer to remain grounded in those rows.

### Step 11: Build the report

The deterministic reporting service adds:

- Row-count insight.
- Numeric range insights.
- A bar-chart recommendation for categorical results.
- A line-chart recommendation for date/time results.

The frontend renders the answer, insights, chart, table, SQL, exports, request ID, and elapsed time.

### Step 12: Write the audit event

The backend appends a JSON object to the configured audit log containing relevant fields such as:

- UTC timestamp.
- Request ID.
- Session ID.
- Question.
- Routing decision.
- Status.
- Generated SQL.
- Returned row count.
- Execution time.

## 7. Agent design

The current application uses a staged, constrained query agent rather than a free-running autonomous agent.

### Intent and policy stage

Classifies metadata, database, chat, and forbidden mutation requests. Critical mutation blocking is deterministic.

### Schema discovery stage

Builds an authoritative schema summary from PostgreSQL and hides restricted domains before inference.

### SQL planner/generator stage

Uses the model and runtime skill to translate a supported business request into one schema-grounded `SELECT`.

### Validation stage

Applies application-level read-only validation, restricted-identifier policies, row limits, and statement rules.

### Execution stage

Executes through the backend’s read-only PostgreSQL pool. The AI provider never receives database credentials and never connects directly to PostgreSQL.

### Analysis stage

Produces a concise natural-language response from real rows and adds deterministic insights and visualization metadata.

### Reporting stage

Renders result tables, charts, SQL, trace information, and downloadable report formats.

These stages are separated by responsibility, but the current repository does **not** yet use LangGraph or multiple independently deployed agents. LangGraph orchestration remains a roadmap item.

## 8. Runtime skill

The agent skill is located at:

```text
backend/app/skills/askme-data-assistant/SKILL.md
```

The backend loads two marked sections from this file at runtime:

- `SQL_RULES`: controls SQL generation.
- `SUMMARY_RULES`: controls result summarization.

Important skill rules include:

- Use only supplied tables and columns.
- Preserve an explicitly named real table.
- Never substitute a familiar but nonexistent identifier.
- Generate one `SELECT` and nothing else.
- Never expose credentials or secret fields.
- Never propose mutation SQL, even as an example.
- Use explicit foreign-key joins.
- Respect row-cap semantics.
- Summarize only authoritative returned rows.
- Never invent business values, counts, dates, names, or statuses.

The skill improves model behavior but does not replace deterministic security controls.

## 9. AI model

The default model is configured through:

```env
CF_AI_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
```

The backend calls the Cloudflare Workers AI REST endpoint:

```text
POST /client/v4/accounts/{account_id}/ai/run/{model}
```

The model performs three bounded tasks:

1. Decide whether a non-deterministic message requires SQL.
2. Generate or correct a read-only SQL statement.
3. Summarize returned rows in business language.

The model cannot access database credentials, open database connections, or execute SQL itself.

## 10. Security model

### Read-only enforcement

- Mutation intent is blocked before inference.
- Generated statements must be `SELECT` queries.
- Multiple statements are rejected.
- Forbidden keywords are rejected.
- PostgreSQL sessions request read-only transaction behavior.
- The database account should have read-only grants.

### Restricted data

Restricted domains are configured as comma-separated values:

```env
RESTRICTED_TABLES=payroll,hr_employees
RESTRICTED_COLUMNS=password,key_secret,ssn,national_id,card_number
```

Restricted identifiers are removed during schema discovery and checked again before execution.

### Resource controls

```env
MAX_ROWS=50
DB_CONNECT_TIMEOUT_SECONDS=10
DB_STATEMENT_TIMEOUT_MS=30000
CF_AI_TIMEOUT_SECONDS=60
```

### API protection

For a local pilot, `ASKME_API_KEY` may be empty. For a shared environment, configure it and place the backend behind organizational authentication. A browser-visible shared key is not a substitute for SSO and role-based access control.

### Auditability

Audit output defaults to:

```text
backend/logs/audit.jsonl
```

Protect this file as sensitive operational data because it contains user questions and generated SQL.

## 11. API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Application and configuration health |
| `GET` | `/api/db/ping` | Database reachability and metadata |
| `GET` | `/api/db/tables` | Approved base tables in the configured schema |
| `POST` | `/api/schema/refresh` | Refresh cached schema metadata |
| `POST` | `/api/chat` | Execute the query-agent workflow |
| `POST` | `/api/chat/reset` | Clear backend memory for one conversation |

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

## 12. Configuration

Backend configuration is loaded from `backend/.env`.

Important variables:

```env
APP_ENV=development
CORS_ORIGINS=http://localhost:5173
ASKME_API_KEY=
EXPOSE_SQL=true
MAX_ROWS=50
MAX_HISTORY_TURNS=8
SCHEMA_CACHE_SECONDS=600

CF_ACCOUNT_ID=your_account_id
CF_API_TOKEN=your_api_token
CF_AI_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
CF_AI_TEMPERATURE=0.1
CF_AI_TIMEOUT_SECONDS=60

DB_URL=postgresql://localhost:5432/ai_query_test
DB_USER=your_read_only_user
DB_PASSWORD=your_password
DB_SCHEMA=ai_demo
DB_POOL_SIZE=5
DB_CONNECT_TIMEOUT_SECONDS=10
DB_STATEMENT_TIMEOUT_MS=30000

RESTRICTED_TABLES=payroll,hr_employees
RESTRICTED_COLUMNS=password,key_secret,ssn,national_id,card_number
AUDIT_LOG_PATH=logs/audit.jsonl
```

Never commit real credentials. Environment files are excluded through `.gitignore`.

## 13. Local development

### Backend

```bat
cd C:\Users\Dell\Downloads\AskMe-Web\backend
..\.venv\Scripts\activate
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bat
cd C:\Users\Dell\Downloads\AskMe-Web\frontend
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

## 14. Testing

### Backend tests

```bat
cd C:\Users\Dell\Downloads\AskMe-Web\backend
..\.venv\Scripts\python.exe -m pytest -q
```

The suite covers configuration parsing, SQL safety, restricted identifiers, schema filtering behavior, query-agent heuristics, runtime-skill loading, and API health.

### Frontend production build

```bat
cd C:\Users\Dell\Downloads\AskMe-Web\frontend
npm.cmd run build
```

### Recommended end-to-end test

```text
Show monthly transaction count and total transaction amount for each transaction type during the latest six months. Compare the trends, highlight the strongest and weakest month, and prepare the results for export.
```

Also test:

- A deterministic table-list request.
- A conversational follow-up.
- An empty result.
- CSV, Excel, and PDF export.
- SQL copying.
- A restricted-column request.
- A destructive request such as `DROP TABLE`.

## 15. Known limitations

- SQL validation is defense in depth but is not yet based on a full PostgreSQL AST parser.
- Conversation messages are persisted in browser storage; backend context is held in process memory.
- Multiple backend workers do not share conversation state.
- Audit storage is a local JSONL file rather than a centralized audit database.
- The chart engine is intentionally lightweight and supports bar and line charts.
- Excel export uses an Excel-compatible HTML `.xls` document rather than native `.xlsx` generation.
- PDF export uses the browser print dialog.
- Executive insights are currently deterministic ranges and row counts plus the model summary; advanced anomaly attribution is not implemented.
- There is no user identity, SSO, RBAC, or row-level authorization layer yet.
- There is no semantic vector catalog or business glossary retrieval yet.
- There is no automated golden-query correctness evaluation yet.
- The current workflow is staged but is not implemented with LangGraph.

## 16. Roadmap

### Phase 1: Validation and governance

- PostgreSQL AST-based query parsing.
- Allowlisted functions and schemas.
- Query cost estimation with `EXPLAIN` before execution.
- Central audit database and searchable audit UI.
- SSO, RBAC, and per-domain authorization.
- PII classification and masking policies.

### Phase 2: Metadata intelligence

- Business glossary and metric definitions.
- Table and column descriptions.
- Data grain and ownership metadata.
- Semantic schema retrieval.
- Join-path ranking.
- Metadata freshness monitoring.

### Phase 3: Multi-agent orchestration

- LangGraph state graph.
- Explicit intent, discovery, planning, SQL, validation, analysis, and reporting nodes.
- Conditional retries and human-review checkpoints.
- Durable conversation and workflow state.

### Phase 4: Reporting

- Native `.xlsx` generation.
- Server-rendered PDF reports.
- Additional visualization types.
- KPI cards, period comparisons, anomaly detection, and narrative trend analysis.
- Saved reports and scheduled distribution.

### Phase 5: Quality measurement

- Golden natural-language/SQL dataset.
- Execution-result equivalence scoring.
- Target of at least 85% SQL correctness.
- Security red-team suite.
- Latency, cost, and answer-grounding dashboards.

## 17. Definition of success

AskMe succeeds when an authorized business user can ask a question in plain language and receive a timely, correct, explainable, exportable answer without writing SQL, while every executed statement remains read-only, policy-compliant, resource-limited, and auditable.
