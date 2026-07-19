# Migration from the Telegram/MySQL project

| Original TypeScript file | New web-project location | Responsibility |
|---|---|---|
| `src/index.ts` | `backend/app/api/routes/chat.py`, `backend/app/api/routes/system.py`, `frontend/src/App.tsx` | Replaces Telegram handlers with HTTP endpoints and React controls |
| `src/ai.ts` | `backend/app/services/ai.py` | Calls Cloudflare Workers AI through its REST API |
| `src/config.ts` | `backend/app/core/config.py` | Loads Pydantic settings and parses PostgreSQL URLs |
| `src/db.ts` | `backend/app/services/database.py` | Creates a psycopg pool and enforces SELECT-only validation, read-only sessions, limits, and timeouts |
| `src/schema.ts` | `backend/app/services/schema.py` | Reads PostgreSQL `information_schema`, marks keys, foreign keys, and hides secrets |
| `src/dataQuery.ts` | `backend/app/services/query_agent.py` | Routes data/chat messages, generates PostgreSQL SQL, retries once, and summarizes rows |
| `src/format.ts` | `frontend/src/components/DataTable.tsx`, `MessageCard.tsx` | Renders browser result tables instead of Telegram HTML |
| `src/prompts/query-agent.md` | `backend/app/skills/askme-data-assistant/SKILL.md` | Replaces the incomplete prompt with PostgreSQL runtime rules |
| `src/scripts/dbping.ts` | `backend/app/scripts/dbping.py` | Tests PostgreSQL connectivity |
| `src/scripts/ask.ts` | `backend/app/scripts/ask.py` | Tests a natural-language query from the terminal |

The frontend stores the session ID and displayed messages in `localStorage`. PostgreSQL and Cloudflare credentials remain only in the backend environment.
