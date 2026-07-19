# Architecture

```text
React browser
    │
    │ POST /api/chat
    ▼
FastAPI + Pydantic
    │
    ├─ Session history (last 8 turns, in process)
    ├─ PostgreSQL schema summary (10-minute cache)
    ├─ SKILL.md runtime prompt rules
    │
    ▼
Cloudflare Workers AI
    │ proposes one PostgreSQL SELECT
    ▼
Secret-column guard + SQL validator
    │
    ▼
psycopg connection pool
    │ read-only session + statement timeout
    ▼
PostgreSQL role with SELECT privileges
    │ real rows, maximum 50 by default
    ▼
Cloudflare Workers AI grounded summary
    │
    ▼
React answer card + responsive result table
```

## Trust boundaries

- The browser never receives PostgreSQL or Cloudflare credentials.
- The model never receives credentials and has no direct database connection.
- The model sees only a compact live schema with secret columns removed.
- The backend executes only validated `SELECT` statements.
- PostgreSQL sessions use `default_transaction_read_only=on` and a statement timeout.
- The configured PostgreSQL role should independently enforce minimum read-only access.
