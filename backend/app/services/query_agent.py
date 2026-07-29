from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import ForbiddenQueryError, UnsupportedDataQuestionError
from app.models.api import ChatMessage
from app.services.ai import workers_ai
from app.services.database import database_service
from app.services.cost_guard import query_cost_guard
from app.services.prompt_loader import load_skill_prompts
from app.services.query_checker import query_checker
from app.services.result_verifier import verify_result
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
TABLE_DEFINITION_REQUEST_RE = re.compile(
    r"\b(definition|define|describe|description|explain|meaning|purpose)\b.*\btables?\b|"
    r"\bwhat\s+(?:does|do|is|are)\b.*\btables?\b.*\b(?:mean|for|store|contain)\b|"
    r"\bwhat\s+is\s+each\s+table\s+for\b",
    re.IGNORECASE,
)
TABLE_DEFINITION_FOLLOWUP_RE = re.compile(
    r"^\s*(?:what\s+are\s+they|describe\s+them|explain\s+them|what\s+do\s+they\s+do)\s*[?.!]*\s*$",
    re.IGNORECASE,
)
DATABASE_NAME_REQUEST_RE = re.compile(
    r"\b(?:what|which)\b.*\bdatabase\s+name\b|\bname\s+of\s+(?:the\s+)?database\b",
    re.IGNORECASE,
)
SCHEMA_QUESTION_RE = re.compile(
    r"\b(schema|table|column|field|variable|attribute|data\s+type|primary\s+key|"
    r"foreign\s+key|relationship|definition|meaning|purpose|metadata|data\s+dictionary)\b",
    re.IGNORECASE,
)
SCHEMA_EXPLANATION_RE = re.compile(
    r"\b(what|which|where|define|describe|explain|mean|means|meaning|purpose|difference|"
    r"relationship|variable|column|field|attribute|metadata)\b",
    re.IGNORECASE,
)
IDENTIFIER_MEANING_RE = re.compile(
    r"\bwhat\s+(?:does|is)\s+[A-Za-z_][A-Za-z0-9_]*\s+(?:mean|for)\b",
    re.IGNORECASE,
)
FOLLOW_UP_RE = re.compile(
    r"^\s*(?:and\b|also\b|only\b|now\b|then\b|what about\b|how about\b|"
    r"show (?:it|them)\b|break it\b|group it\b|filter it\b|sort it\b|"
    r"those\b|these\b|they\b|them\b|it\b)",
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


def unsupported_reason(value: str) -> str | None:
    match = re.match(r"^\s*UNSUPPORTED\s*:\s*(.+)$", value, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def looks_like_data_question(text: str) -> bool:
    return bool(DATA_QUESTION_RE.search(text))


def looks_like_destructive_request(text: str) -> bool:
    """Reject requests to generate or execute database-changing SQL."""
    return bool(DESTRUCTIVE_REQUEST_RE.search(text))


def looks_like_table_list_request(text: str) -> bool:
    return bool(TABLE_LIST_REQUEST_RE.search(text))


def looks_like_table_definition_request(
    text: str,
    history: list[ChatMessage] | None = None,
) -> bool:
    if TABLE_DEFINITION_REQUEST_RE.search(text):
        return True
    if not TABLE_DEFINITION_FOLLOWUP_RE.match(text):
        return False
    return any(
        message.role == "assistant" and "tables in the" in message.content.lower()
        for message in (history or [])[-4:]
    )


def looks_like_database_name_request(text: str) -> bool:
    return bool(DATABASE_NAME_REQUEST_RE.search(text))


def looks_like_schema_question(text: str) -> bool:
    return bool(
        IDENTIFIER_MEANING_RE.search(text)
        or
        SCHEMA_QUESTION_RE.search(text)
        and SCHEMA_EXPLANATION_RE.search(text)
    )


def looks_degenerate(text: str) -> bool:
    value = text.strip()
    if not value:
        return True
    if re.search(r"(.{2,20}?)\1{5,}", value, re.DOTALL):
        return True
    words = value.split()
    return len(words) >= 12 and len(set(words)) / len(words) < 0.35


def generation_history(
    question: str,
    history: list[ChatMessage],
) -> list[ChatMessage]:
    """Use prior turns only when the new message is clearly a follow-up."""
    return history[-4:] if FOLLOW_UP_RE.search(question) else []


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
    def __init__(self) -> None:
        self._successful_plans: dict[tuple[str, str], str] = {}

    @staticmethod
    def _plan_key(question: str, schema_name: str) -> tuple[str, str]:
        normalized = re.sub(r"\s+", " ", question).strip().casefold().rstrip("?.!")
        return schema_name.casefold(), normalized

    async def _answer_schema_question(
        self,
        question: str,
        selected_schema: str,
        history: list[ChatMessage],
    ) -> RouteAnswer:
        settings = get_settings()
        prompts = load_skill_prompts(settings.max_rows)
        metadata = await schema_service.get_metadata_context(question, selected_schema)
        messages = [
            ChatMessage(role="system", content=prompts.metadata_rules),
            *history[-4:],
            ChatMessage(
                role="user",
                content=(
                    f"Database: {settings.database.database}\n"
                    f"{metadata}\n\nQuestion: {question}"
                ),
            ),
        ]
        answer = (await workers_ai.chat(messages)).strip()
        return RouteAnswer(kind="data", answer=answer, rows=[], sql=None)

    async def answer_metadata(
        self,
        question: str,
        schema_name: str | None = None,
        history: list[ChatMessage] | None = None,
    ) -> RouteAnswer | None:
        """Answer common database metadata requests without model inference."""
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema_name)
        if looks_like_database_name_request(question):
            database_name = settings.database.database
            return RouteAnswer(
                kind="data",
                answer=f"The database name is {database_name}.",
                rows=[{"database_name": database_name}],
                sql="SELECT current_database() AS database_name",
            )
        if (
            looks_like_table_definition_request(question, history)
            or (
                looks_like_schema_question(question)
                and not looks_like_table_list_request(question)
            )
        ):
            return await self._answer_schema_question(
                question,
                selected_schema,
                history or [],
            )
        if looks_like_table_list_request(question):
            names = await database_service.list_tables(selected_schema)
            rows = [{"table_name": name} for name in names]
            answer = (
                f"Found {len(names)} tables in the {selected_schema} schema."
                if names
                else f"No base tables were found in the {selected_schema} schema."
            )
            schema_literal = selected_schema.replace("'", "''")
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
        if unsupported_reason(sql):
            return sql
        return sql if re.match(r"^select\b", sql, re.IGNORECASE) else None

    async def _run_guarded(self, sql: str, schema_name: str) -> list[dict[str, Any]]:
        if references_secret_column(sql):
            raise ForbiddenQueryError()
        checked = await query_checker.check(sql, schema_name)
        await query_cost_guard.check(checked.normalized_sql, schema_name)
        return await database_service.run_select_in_schema(checked.normalized_sql, schema_name)

    async def _run_with_retry(
        self,
        question: str,
        schema: str,
        first_sql: str,
        history: list[ChatMessage],
        schema_name: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        settings = get_settings()
        sql = first_sql
        attempted: set[str] = set()
        active_schema = schema

        for attempt in range(1, max(1, settings.sql_max_attempts) + 1):
            reason = unsupported_reason(sql)
            if reason and attempt < settings.sql_max_attempts:
                # Re-check model claims against the complete approved catalog.
                active_schema = await schema_service.get_relevant_summary(
                    question,
                    schema=schema_name,
                    additional_terms=question,
                    max_tables=50,
                    force=True,
                )
                sql = await self._generate_sql(
                    question,
                    active_schema,
                    [],
                    (
                        f"The previous response claimed this was unsupported: {reason}. "
                        "Verify that claim against the complete approved schema. Return "
                        "a SELECT if the fields exist; otherwise return UNSUPPORTED with "
                        "the exact missing field."
                    ),
                )
                continue
            if reason:
                raise UnsupportedDataQuestionError(
                    f"I can’t answer this from the {schema_name} schema because {reason}"
                )
            normalized_key = re.sub(r"\s+", " ", sql).strip().lower()
            if normalized_key in attempted:
                raise UnsupportedDataQuestionError(
                    f"I couldn’t generate a different valid SELECT for the {schema_name} "
                    "schema. The requested field or relationship may not exist in its "
                    "approved metadata."
                )
            attempted.add(normalized_key)
            try:
                rows = await self._run_guarded(sql, schema_name)
                verification = verify_result(question, sql, rows)
                if not verification.passed:
                    raise ValueError(
                        "Result verification failed: " + "; ".join(verification.issues)
                    )
                self._successful_plans[self._plan_key(question, schema_name)] = sql
                return sql, rows
            except ForbiddenQueryError:
                raise
            except Exception as exc:
                # Connectivity exceptions are never retried as SQL-generation mistakes.
                from app.core.errors import DatabaseUnavailableError

                if isinstance(exc, DatabaseUnavailableError) or attempt >= settings.sql_max_attempts:
                    raise
                active_schema = await schema_service.get_relevant_summary(
                    question,
                    schema=schema_name,
                    additional_terms=f"{sql}\n{exc}",
                    max_tables=settings.schema_max_tables * (attempt + 1),
                )
                error_context = (
                    f"Attempt {attempt} of {settings.sql_max_attempts} failed before or "
                    f"during read-only execution: {exc}. Inspect the refreshed approved "
                    "schema, correct the table/column/join, and do not repeat prior SQL."
                )
                sql = await self._generate_sql(
                    question,
                    active_schema,
                    history,
                    error_context,
                )

        raise ValueError("SQL generation attempts were exhausted.")

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
        schema_name: str | None = None,
    ) -> DataAnswer:
        selected_schema = get_settings().resolve_schema(schema_name)
        prior = history or []
        relevant_history = generation_history(question, prior)
        history_terms = " ".join(
            message.content for message in relevant_history if message.role == "user"
        )
        schema = await schema_service.get_relevant_summary(
            question,
            schema=selected_schema,
            additional_terms=history_terms,
        )
        first_sql = self._successful_plans.get(
            self._plan_key(question, selected_schema)
        ) or await self._generate_sql(question, schema, relevant_history)
        sql, rows = await self._run_with_retry(
            question, schema, first_sql, relevant_history, selected_schema
        )
        answer = await self._summarize(question, sql, rows)
        return DataAnswer(question=question, sql=sql, answer=answer, rows=rows)

    async def answer_message(
        self,
        text: str,
        history: list[ChatMessage],
        system_prompt: str,
        schema_name: str | None = None,
    ) -> RouteAnswer:
        from app.core.errors import ConfigurationError, DatabaseUnavailableError

        selected_schema = get_settings().resolve_schema(schema_name)
        relevant_history = generation_history(text, history)
        try:
            history_terms = " ".join(
                message.content for message in relevant_history if message.role == "user"
            )
            schema = await schema_service.get_relevant_summary(
                text,
                schema=selected_schema,
                additional_terms=history_terms,
            )
        except (DatabaseUnavailableError, ConfigurationError):
            if looks_like_data_question(text):
                raise
            return await self._chat(text, history, system_prompt)

        first_sql = self._successful_plans.get(self._plan_key(text, selected_schema))
        if first_sql is None:
            first_sql = await self._generate_sql_or_chat(
                text, schema, relevant_history
            )
        if first_sql is None and looks_like_data_question(text):
            forced = await self._generate_sql(text, schema, relevant_history)
            if re.match(r"^select\b", forced, re.IGNORECASE):
                first_sql = forced

        if first_sql is None:
            return await self._chat(text, history, system_prompt)

        sql, rows = await self._run_with_retry(
            text, schema, first_sql, relevant_history, selected_schema
        )
        answer = await self._summarize(text, sql, rows)
        return RouteAnswer(kind="data", answer=answer, sql=sql, rows=rows)


query_agent = QueryAgent()
