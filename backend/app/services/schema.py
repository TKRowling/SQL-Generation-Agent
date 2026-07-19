from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from app.core.config import get_settings
from app.services.database import database_service


SECRET_COLUMNS = {"key_secret", "password"}


def simplify_type(value: str) -> str:
    return value.replace(" without time zone", "").replace(" with time zone", "tz").strip()


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


class SchemaService:
    def __init__(self) -> None:
        self._cached_text: str | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def get_summary(self, force: bool = False) -> str:
        settings = get_settings()
        now = time.monotonic()
        if (
            not force
            and self._cached_text is not None
            and now - self._cached_at < settings.schema_cache_seconds
        ):
            return self._cached_text

        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._cached_text is not None
                and now - self._cached_at < settings.schema_cache_seconds
            ):
                return self._cached_text

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
                [settings.db_schema],
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
                [settings.db_schema],
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
            self._cached_text = text
            self._cached_at = now
            return text


schema_service = SchemaService()
