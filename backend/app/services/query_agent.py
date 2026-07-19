from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import ForbiddenQueryError
from app.models.api import ChatMessage
from app.services.ai import workers_ai
from app.services.database import database_service
from app.services.prompt_loader import load_skill_prompts
from app.services.schema import schema_service


SECRET_COLUMN_RE = re.compile(r"\b(key_secret|password)\b", re.IGNORECASE)
DATA_QUESTION_RE = re.compile(
    r"\b(how many|how much|count|number of|list|show|total|average|sum|top\s+\d+|"
    r"most|recent|latest|expired|revoked|created|status|documents?|projects?|"
    r"organi[sz]ations?|users?|keys?|issuers?|records?|rows?|tables?)\b",
    re.IGNORECASE,
)
DESTRUCTIVE_REQUEST_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|replace|"
    r"copy|call|execute|vacuum|reindex|cluster|refresh)\b",
    re.IGNORECASE,
)
TABLE_LIST_REQUEST_RE = re.compile(
    r"\b(?:list|show|display)\b.*\b(?:all\s+(?:the\s+)?tables?|tables|table\s+names)\b|"
    r"\b(?:what|which)\b.*\btables?\b|"
    r"\bwhat\s+tables?\s+(?:are|is)\b",
    re.IGNORECASE,
)
DATABASE_NAME_REQUEST_RE = re.compile(
    r"\b(?:what|which)\b.*\bdatabase\s+name\b|\bname\s+of\s+(?:the\s+)?database\b",
    re.IGNORECASE,
)


@dataclass
class DataAnswer:
    question: str
    sql: str
    answer: str
    rows: list[dict[str, Any]]

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass
class RouteAnswer:
    kind: str
    answer: str
    rows: list[dict[str, Any]]
    sql: str | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)


def references_secret_column(sql: str) -> bool:
    return bool(SECRET_COLUMN_RE.search(sql))


def extract_sql(raw: str) -> str:
    value = raw.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", value, re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    if ";" in value:
        value = value.split(";", 1)[0]
    return value.strip()


def looks_like_data_question(text: str) -> bool:
    return bool(DATA_QUESTION_RE.search(text))


def looks_like_destructive_request(text: str) -> bool:
    """Reject requests to generate or execute database-changing SQL."""
    return bool(DESTRUCTIVE_REQUEST_RE.search(text))


def looks_like_table_list_request(text: str) -> bool:
    return bool(TABLE_LIST_REQUEST_RE.search(text))


def looks_like_database_name_request(text: str) -> bool:
    return bool(DATABASE_NAME_REQUEST_RE.search(text))


def looks_degenerate(text: str) -> bool:
    value = text.strip()
    if not value:
        return True
    if re.search(r"(.{2,20}?)\1{5,}", value, re.DOTALL):
        return True
    words = value.split()
    return len(words) >= 12 and len(set(words)) / len(words) < 0.35


def labelize(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split("_"))


def deterministic_summary(rows: list[dict[str, Any]], capped: bool) -> str:
    if not rows:
        return "No matching records were found."
    if len(rows) == 1:
        entries = list(rows[0].items())
        if len(entries) == 1:
            key, value = entries[0]
            return f"{labelize(key)}: {value if value is not None else '—'}"
        return ", ".join(
            f"{labelize(key)}: {value if value is not None else '—'}"
            for key, value in entries
        )
    if capped:
        return f"Here are the first {len(rows)} results (there are more):"
    return f"Here are the {len(rows)} results:"


class QueryAgent:
    async def answer_metadata(self, question: str) -> RouteAnswer | None:
        """Answer common database metadata requests without model inference."""
        settings = get_settings()
        if looks_like_database_name_request(question):
            database_name = settings.database.database
            return RouteAnswer(
                kind="data",
                answer=f"The database name is {database_name}.",
                rows=[{"database_name": database_name}],
                sql="SELECT current_database() AS database_name",
            )
        if looks_like_table_list_request(question):
            names = await database_service.list_tables()
            rows = [{"table_name": name} for name in names]
            answer = (
                f"Found {len(names)} tables in the {settings.db_schema} schema."
                if names
                else f"No base tables were found in the {settings.db_schema} schema."
            )
            schema_literal = settings.db_schema.replace("'", "''")
            return RouteAnswer(
                kind="data",
                answer=answer,
                rows=rows,
                sql=(
                    "SELECT table_name FROM information_schema.tables "
                    f"WHERE table_schema = '{schema_literal}' "
                    "AND table_type = 'BASE TABLE' ORDER BY table_name"
                ),
            )
        return None

    def _sql_system_prompt(self, schema: str) -> str:
        settings = get_settings()
        prompts = load_skill_prompts(settings.max_rows)
        return (
            f"{prompts.sql_rules}\n\n"
            "Schema (table: column type [PK|UNI] [->fk]):\n"
            f"{schema}"
        )

    def _route_system_prompt(self, schema: str) -> str:
        return (
            f"{self._sql_system_prompt(schema)}\n\n"
            "Default to writing SQL. A request mentioning data, counts, lists, totals, "
            "breakdowns, statistics, overviews, a table/entity name, grouped by, per, "
            "by status, how many, top, or each is a data question. Return a SELECT.\n"
            "Output exactly NO_QUERY only for messages unrelated to the database, such "
            "as greetings, thanks, small talk, opinions, or general knowledge. When "
            "uncertain, prefer a SELECT over NO_QUERY."
        )

    async def _generate_sql(
        self,
        question: str,
        schema: str,
        history: list[ChatMessage],
        prior_error: str | None = None,
    ) -> str:
        system = self._sql_system_prompt(schema)
        if prior_error:
            system += (
                "\n\nThe previous query failed with this database error:\n"
                f"{prior_error}\nReturn one corrected SELECT only."
            )
        messages = [ChatMessage(role="system", content=system), *history]
        messages.append(ChatMessage(role="user", content=question))
        return extract_sql(await workers_ai.chat(messages))

    async def _generate_sql_or_chat(
        self,
        text: str,
        schema: str,
        history: list[ChatMessage],
    ) -> str | None:
        messages = [ChatMessage(role="system", content=self._route_system_prompt(schema)), *history]
        messages.append(ChatMessage(role="user", content=text))
        raw = await workers_ai.chat(messages)
        if "NO_QUERY" in raw.upper():
            return None
        sql = extract_sql(raw)
        return sql if re.match(r"^select\b", sql, re.IGNORECASE) else None

    async def _run_guarded(self, sql: str) -> list[dict[str, Any]]:
        if references_secret_column(sql):
            raise ForbiddenQueryError()
        return await database_service.run_select(sql)

    async def _run_with_retry(
        self,
        question: str,
        schema: str,
        first_sql: str,
        history: list[ChatMessage],
    ) -> tuple[str, list[dict[str, Any]]]:
        sql = first_sql
        try:
            return sql, await self._run_guarded(sql)
        except ForbiddenQueryError:
            raise
        except Exception as exc:
            # Connectivity exceptions are converted by DatabaseService and should not
            # be retried as SQL-generation mistakes.
            from app.core.errors import DatabaseUnavailableError

            if isinstance(exc, DatabaseUnavailableError):
                raise
            sql = await self._generate_sql(question, schema, history, str(exc))
            return sql, await self._run_guarded(sql)

    async def _summarize(
        self,
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
    ) -> str:
        settings = get_settings()
        prompts = load_skill_prompts(settings.max_rows)
        capped = len(rows) >= settings.max_rows
        count_note = (
            f"Row count: {len(rows)} (CAPPED at {settings.max_rows}; these are only the "
            f"first {settings.max_rows} rows and the true total is unknown. Do not state "
            f"{len(rows)} as the total.)"
            if capped
            else f"Row count: {len(rows)} (complete authoritative result; not truncated)."
        )
        payload = json.dumps(rows, ensure_ascii=False, default=str)[:4000]
        messages = [
            ChatMessage(role="system", content=prompts.summary_rules),
            ChatMessage(
                role="user",
                content=(
                    f"Question: {question}\nSQL: {sql}\n{count_note}\n"
                    f"Rows (JSON, individual values may be truncated): {payload}"
                ),
            ),
        ]
        answer = (await workers_ai.chat(messages)).strip()
        return deterministic_summary(rows, capped) if looks_degenerate(answer) else answer

    async def _chat(
        self,
        text: str,
        history: list[ChatMessage],
        system_prompt: str,
    ) -> RouteAnswer:
        messages = [ChatMessage(role="system", content=system_prompt), *history]
        messages.append(ChatMessage(role="user", content=text))
        return RouteAnswer(kind="chat", answer=(await workers_ai.chat(messages)).strip(), rows=[])

    async def answer_data_question(
        self,
        question: str,
        history: list[ChatMessage] | None = None,
    ) -> DataAnswer:
        prior = history or []
        schema = await schema_service.get_summary()
        first_sql = await self._generate_sql(question, schema, prior)
        sql, rows = await self._run_with_retry(question, schema, first_sql, prior)
        answer = await self._summarize(question, sql, rows)
        return DataAnswer(question=question, sql=sql, answer=answer, rows=rows)

    async def answer_message(
        self,
        text: str,
        history: list[ChatMessage],
        system_prompt: str,
    ) -> RouteAnswer:
        from app.core.errors import ConfigurationError, DatabaseUnavailableError

        try:
            schema = await schema_service.get_summary()
        except (DatabaseUnavailableError, ConfigurationError):
            if looks_like_data_question(text):
                raise
            return await self._chat(text, history, system_prompt)

        first_sql = await self._generate_sql_or_chat(text, schema, history)
        if first_sql is None and looks_like_data_question(text):
            forced = await self._generate_sql(text, schema, history)
            if re.match(r"^select\b", forced, re.IGNORECASE):
                first_sql = forced

        if first_sql is None:
            return await self._chat(text, history, system_prompt)

        sql, rows = await self._run_with_retry(text, schema, first_sql, history)
        answer = await self._summarize(text, sql, rows)
        return RouteAnswer(kind="data", answer=answer, sql=sql, rows=rows)


query_agent = QueryAgent()
