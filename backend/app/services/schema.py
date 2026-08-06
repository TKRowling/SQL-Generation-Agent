from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.services.database import database_service


SECRET_COLUMNS = {"key_secret", "password"}
WORD_RE = re.compile(r"[a-z0-9]+")
SEMANTIC_SYNONYMS = {
    "client": {"customer"},
    "clients": {"customer"},
    "customer": {"client"},
    "customers": {"client"},
    "earnings": {"income", "amount"},
    "salary": {"income", "amount"},
    "income": {"earnings", "amount"},
    "office": {"branch"},
    "location": {"branch", "address"},
    "payment": {"transaction", "amount"},
    "payments": {"transaction", "amount"},
    "loan": {"application", "credit"},
    "loans": {"application", "credit"},
    "risk": {"score", "fraud"},
    "balance": {"amount", "account"},
}


@dataclass(frozen=True)
class SchemaCatalog:
    columns: dict[str, frozenset[str]]
    foreign_keys: tuple[dict[str, Any], ...]

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.columns))


def simplify_type(value: str) -> str:
    return value.replace(" without time zone", "").replace(" with time zone", "tz").strip()


def infer_table_definition(table_name: str) -> str:
    subject = table_name.replace("_", " ").strip()
    if subject.endswith(" history"):
        return f"Stores historical {subject.removesuffix(' history')} changes and events."
    if subject.endswith(" relationships"):
        return f"Stores relationships between {subject.removesuffix(' relationships')} records."
    return f"Stores records related to {subject}."


def build_schema_summary(columns: list[dict[str, Any]], foreign_keys: list[dict[str, Any]]) -> str:
    fk_map = {
        f"{row['table_name']}.{row['column_name']}": f"{row['ref_table']}.{row['ref_column']}"
        for row in foreign_keys
    }
    grouped: dict[str, list[str]] = defaultdict(list)

    for column in columns:
        column_name = str(column["column_name"])
        if column_name.lower() in SECRET_COLUMNS:
            continue
        table_name = str(column["table_name"])
        key = (
            " PK"
            if column.get("column_key") == "PRI"
            else " UNI"
            if column.get("column_key") == "UNI"
            else ""
        )
        ref = fk_map.get(f"{table_name}.{column_name}")
        fk_text = f" ->{ref}" if ref else ""
        grouped[table_name].append(
            f"{column_name} {simplify_type(str(column['column_type']))}{key}{fk_text}"
        )

    return "\n".join(f"{table}: {', '.join(parts)}" for table, parts in grouped.items())


def select_relevant_tables(
    question: str,
    catalog: SchemaCatalog,
    max_tables: int,
    additional_terms: str = "",
) -> list[str]:
    """Rank approved tables lexically, then include useful FK neighbours."""
    searchable = f"{question} {additional_terms}".lower().replace("_", " ")
    words = set(WORD_RE.findall(searchable))
    semantic_words = set(words)
    for word in words:
        semantic_words.update(SEMANTIC_SYNONYMS.get(word, set()))
    scores: dict[str, int] = {}

    for table, columns in catalog.columns.items():
        table_words = set(WORD_RE.findall(table.replace("_", " ")))
        score = 0
        if table.lower() in f"{question.lower()} {additional_terms.lower()}":
            score += 20
        score += 5 * len(table_words & semantic_words)
        for column in columns:
            column_words = set(WORD_RE.findall(column.replace("_", " ")))
            score += min(3, len(column_words & semantic_words))
        if score:
            scores[table] = score

    if not scores:
        return list(catalog.table_names[:max_tables])

    selected = [
        table for table, _ in
        sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:max_tables]
    ]
    neighbours: list[str] = []
    selected_set = set(selected)
    for fk in catalog.foreign_keys:
        table = str(fk["table_name"])
        ref_table = str(fk["ref_table"])
        if table in selected_set and ref_table not in selected_set:
            neighbours.append(ref_table)
        elif ref_table in selected_set and table not in selected_set:
            neighbours.append(table)
    for table in neighbours:
        if table in catalog.columns and table not in selected_set and len(selected) < max_tables:
            selected.append(table)
            selected_set.add(table)
    return selected


class SchemaService:
    def __init__(self) -> None:
        self._cached_text: dict[str, str] = {}
        self._cached_columns: dict[str, list[dict[str, Any]]] = {}
        self._cached_foreign_keys: dict[str, list[dict[str, Any]]] = {}
        self._cached_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_summary(self, schema: str | None = None, force: bool = False) -> str:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        now = time.monotonic()
        if (
            not force
            and selected_schema in self._cached_text
            and now - self._cached_at.get(selected_schema, 0) < settings.schema_cache_seconds
        ):
            return self._cached_text[selected_schema]

        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and selected_schema in self._cached_text
                and now - self._cached_at.get(selected_schema, 0) < settings.schema_cache_seconds
            ):
                return self._cached_text[selected_schema]

            columns = await database_service.execute_internal(
                """
                SELECT
                    c.table_name,
                    c.column_name,
                    CASE
                        WHEN c.character_maximum_length IS NOT NULL
                            THEN c.data_type || '(' || c.character_maximum_length::text || ')'
                        WHEN c.numeric_precision IS NOT NULL AND c.data_type IN ('numeric', 'decimal')
                            THEN c.data_type || '(' || c.numeric_precision::text || ',' || COALESCE(c.numeric_scale, 0)::text || ')'
                        WHEN c.data_type = 'ARRAY' THEN c.udt_name
                        ELSE c.data_type
                    END AS column_type,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.constraint_schema = kcu.constraint_schema
                            WHERE tc.table_schema = c.table_schema
                              AND tc.table_name = c.table_name
                              AND kcu.column_name = c.column_name
                              AND tc.constraint_type = 'PRIMARY KEY'
                        ) THEN 'PRI'
                        WHEN EXISTS (
                            SELECT 1
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.constraint_schema = kcu.constraint_schema
                            WHERE tc.table_schema = c.table_schema
                              AND tc.table_name = c.table_name
                              AND kcu.column_name = c.column_name
                              AND tc.constraint_type = 'UNIQUE'
                        ) THEN 'UNI'
                        ELSE ''
                    END AS column_key
                FROM information_schema.columns c
                WHERE c.table_schema = %s
                ORDER BY c.table_name, c.ordinal_position
                """,
                [selected_schema],
            )
            foreign_keys = await database_service.execute_internal(
                """
                SELECT
                    kcu.table_name,
                    kcu.column_name,
                    ccu.table_name AS ref_table,
                    ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.constraint_schema = tc.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = %s
                ORDER BY kcu.table_name, kcu.ordinal_position
                """,
                [selected_schema],
            )
            restricted_tables = {
                item.strip().lower() for item in settings.restricted_tables.split(",") if item.strip()
            }
            restricted_columns = SECRET_COLUMNS | {
                item.strip().lower() for item in settings.restricted_columns.split(",") if item.strip()
            }
            columns = [
                row for row in columns
                if str(row["table_name"]).lower() not in restricted_tables
                and str(row["column_name"]).lower() not in restricted_columns
            ]
            foreign_keys = [
                row for row in foreign_keys
                if str(row["table_name"]).lower() not in restricted_tables
                and str(row["ref_table"]).lower() not in restricted_tables
            ]
            text = build_schema_summary(columns, foreign_keys)
            self._cached_text[selected_schema] = text
            self._cached_columns[selected_schema] = columns
            self._cached_foreign_keys[selected_schema] = foreign_keys
            self._cached_at[selected_schema] = now
            return text

    async def get_catalog(self, schema: str | None = None, force: bool = False) -> SchemaCatalog:
        selected_schema = get_settings().resolve_schema(schema)
        await self.get_summary(selected_schema, force=force)
        grouped: dict[str, set[str]] = defaultdict(set)
        for column in self._cached_columns[selected_schema]:
            grouped[str(column["table_name"])].add(str(column["column_name"]))
        return SchemaCatalog(
            columns={table: frozenset(columns) for table, columns in grouped.items()},
            foreign_keys=tuple(dict(row) for row in self._cached_foreign_keys[selected_schema]),
        )

    async def get_fingerprint(self, schema: str | None = None) -> str:
        """Hash the approved schema structure for safe plan-cache invalidation."""
        selected_schema = get_settings().resolve_schema(schema)
        await self.get_summary(selected_schema)
        columns = sorted(
            (
                str(row.get("table_name", "")),
                str(row.get("column_name", "")),
                str(row.get("data_type", "")),
                str(row.get("is_nullable", "")),
                bool(row.get("is_pk")),
                bool(row.get("is_unique")),
            )
            for row in self._cached_columns[selected_schema]
        )
        foreign_keys = sorted(
            (
                str(row.get("table_name", "")),
                str(row.get("column_name", "")),
                str(row.get("ref_table", "")),
                str(row.get("ref_column", "")),
            )
            for row in self._cached_foreign_keys[selected_schema]
        )
        payload = json.dumps(
            {"schema": selected_schema, "columns": columns, "foreign_keys": foreign_keys},
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def get_table_definitions(self, schema: str | None = None) -> list[dict[str, Any]]:
        """Return governed comments when present and clearly marked inferred purposes otherwise."""
        selected_schema = get_settings().resolve_schema(schema)
        await self.get_summary(selected_schema)
        catalog = await self.get_catalog(selected_schema)
        comments = await database_service.execute_internal(
            """
            SELECT c.relname AS table_name,
                   obj_description(c.oid, 'pg_class') AS description
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relkind = 'r'
            ORDER BY c.relname
            """,
            [selected_schema],
        )
        comment_map = {
            str(row["table_name"]): str(row["description"]).strip()
            for row in comments
            if row.get("description")
        }
        return [
            {
                "table_name": table,
                "definition": comment_map.get(table) or infer_table_definition(table),
                "definition_source": "database comment" if table in comment_map else "inferred from table name",
                "example_columns": ", ".join(sorted(catalog.columns[table])[:8]),
            }
            for table in catalog.table_names
        ]

    async def get_metadata_context(self, question: str, schema: str | None = None) -> str:
        """Build a metadata-only context for general schema explanations."""
        selected_schema = get_settings().resolve_schema(schema)
        relevant = await self.get_relevant_summary(question, schema=selected_schema)
        definitions = await self.get_table_definitions(selected_schema)
        column_comments = await database_service.execute_internal(
            """
            SELECT c.relname AS table_name,
                   a.attname AS column_name,
                   col_description(c.oid, a.attnum) AS description
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = %s
              AND c.relkind = 'r'
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND col_description(c.oid, a.attnum) IS NOT NULL
            ORDER BY c.relname, a.attnum
            """,
            [selected_schema],
        )
        definition_lines = [
            f"{row['table_name']}: {row['definition']} "
            f"[source: {row['definition_source']}]"
            for row in definitions
        ]
        comment_lines = [
            f"{row['table_name']}.{row['column_name']}: {row['description']}"
            for row in column_comments
        ]
        return (
            f"Selected schema: {selected_schema}\n"
            f"{relevant}\n"
            "Table definitions:\n"
            + "\n".join(definition_lines)
            + "\nOfficial column comments:\n"
            + ("\n".join(comment_lines) if comment_lines else "(none)")
        )

    async def get_relevant_summary(
        self,
        question: str,
        *,
        schema: str | None = None,
        additional_terms: str = "",
        max_tables: int | None = None,
        force: bool = False,
    ) -> str:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        await self.get_summary(selected_schema, force=force)
        catalog = await self.get_catalog(selected_schema)
        limit = max(1, max_tables or settings.schema_max_tables)
        selected = select_relevant_tables(question, catalog, limit, additional_terms)
        selected_set = set(selected)
        columns = [
            row for row in self._cached_columns[selected_schema]
            if str(row["table_name"]) in selected_set
        ]
        foreign_keys = [
            row for row in self._cached_foreign_keys[selected_schema]
            if str(row["table_name"]) in selected_set
            and str(row["ref_table"]) in selected_set
        ]
        inventory = ", ".join(catalog.table_names)
        summary = build_schema_summary(columns, foreign_keys)
        return (
            f"Approved table inventory (names only): {inventory}\n"
            f"Relevant approved table schemas ({len(selected)}):\n{summary}"
        )


schema_service = SchemaService()
