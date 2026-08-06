# AskMe agent package

This folder contains the small, framework-facing parts of the LangGraph system.

| File | Purpose |
|---|---|
| `state.py` | Shared graph state and the final API-facing result type |
| `tools.py` | Governed LangChain `@tool` interfaces |
| `debug.py` | Safe node timing and transition logs |
| `graph.py` | Agents, graph transitions, and bounded correction loop |

Existing database, schema, SQL-policy, cost, verification, and reporting services stay independent of LangGraph so they can be unit tested directly.

## Debugging

Set this in `backend/.env` and restart FastAPI:

```env
AGENT_DEBUG=true
```

Each node then logs its name, schema, attempt, duration, route, error state, and row count. Questions and SQL are represented only by short SHA-256 hashes; result rows and credentials are never logged.

Useful endpoints:

```text
GET /api/health
GET /api/agent/info
GET /api/db/ping
```

Set `AGENT_DEBUG=false` after troubleshooting, especially outside local development.
