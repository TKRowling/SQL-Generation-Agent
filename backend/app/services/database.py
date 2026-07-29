from __future__ import annotations

import asyncio
import re
import threading
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Iterator, Sequence
from uuid import UUID

import psycopg
from sqlglot import exp, parse
from sqlglot.errors import ParseError
from psycopg.rows import dict_row
from psycopg import sql as psycopg_sql
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.config import get_settings
from app.core.errors import ConfigurationError, DatabaseUnavailableError


FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|replace|"
    r"call|execute|set|reset|copy|vacuum|analyze|reindex|cluster|refresh|do|"
    r"listen|unlisten|notify)\b",
    re.IGNORECASE,
)
LIMIT_RE = re.compile(r"\blimit\b", re.IGNORECASE)
SELECT_RE = re.compile(r"^select\b", re.IGNORECASE)
DB_UNREACHABLE_RE = re.compile(
    r"connection refused|connection reset|connection timed out|could not connect|"
    r"server closed the connection|network is unreachable|name or service not known|"
    r"temporary failure in name resolution|password authentication failed|"
    r"database .* does not exist|role .* does not exist|pool timeout|pool is closed",
    re.IGNORECASE,
)


def normalize_select(sql: str, limit: int) -> str:
    """Defense-in-depth SELECT validation and AST-based row capping."""
    trimmed = sql.strip()
    if FORBIDDEN_SQL_RE.search(trimmed):
        raise ValueError("Query contains a forbidden keyword.")
    try:
        statements = parse(trimmed, read="postgres")
    except ParseError as exc:
        raise ValueError(f"Invalid PostgreSQL SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Only one SELECT query is allowed.")
    statement = statements[0]
    if statement.args.get("limit") is None:
        statement = statement.limit(limit)
    return statement.sql(dialect="postgres")


def enforce_access_policy(sql: str) -> None:
    settings = get_settings()
    restricted = [
        item.strip() for item in
        f"{settings.restricted_tables},{settings.restricted_columns}".split(",")
        if item.strip()
    ]
    for identifier in restricted:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])", sql, re.IGNORECASE):
            raise ValueError(f"Query references restricted identifier: {identifier}")


def is_db_unreachable(error: BaseException) -> bool:
    if isinstance(error, (psycopg.OperationalError, psycopg.InterfaceError, PoolTimeout)):
        return True
    sqlstate = getattr(error, "sqlstate", "") or ""
    if sqlstate.startswith("08") or sqlstate in {"28P01", "3D000", "3F000"}:
        return True
    return bool(DB_UNREACHABLE_RE.search(f"{sqlstate} {error}"))


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


class DatabaseService:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> ConnectionPool:
        if self._pool is not None:
            return self._pool

        with self._pool_lock:
            if self._pool is not None:
                return self._pool

            settings = get_settings()
            try:
                db = settings.database
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from exc

            if not db.user:
                raise ConfigurationError(
                    "Database user is missing. Set DB_USER or include it in DB_URL."
                )

            options = (
                f"-c search_path={settings.db_schema},public "
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={settings.db_statement_timeout_ms}"
            )
            kwargs: dict[str, Any] = {
                "host": db.host,
                "port": db.port,
                "dbname": db.database,
                "user": db.user,
                "password": db.password,
                "connect_timeout": settings.db_connect_timeout_seconds,
                "autocommit": True,
                "row_factory": dict_row,
                "options": options,
            }
            if db.sslmode:
                kwargs["sslmode"] = db.sslmode

            try:
                pool = ConnectionPool(
                    conninfo="",
                    min_size=1,
                    max_size=settings.db_pool_size,
                    kwargs=kwargs,
                    open=False,
                    name="askme_pool",
                )
                pool.open(wait=True, timeout=settings.db_connect_timeout_seconds)
                self._pool = pool
            except Exception as exc:
                if is_db_unreachable(exc):
                    raise DatabaseUnavailableError(str(exc)) from exc
                raise
            return self._pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        try:
            with self._get_pool().connection() as connection:
                yield connection
        except Exception as exc:
            if is_db_unreachable(exc):
                raise DatabaseUnavailableError(str(exc)) from exc
            raise

    def _execute_sync(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, tuple(params or ()))
                    rows = cursor.fetchall()
                    return [json_safe(dict(row)) for row in rows]
        except Exception as exc:
            if is_db_unreachable(exc):
                raise DatabaseUnavailableError(str(exc)) from exc
            raise

    async def execute_internal(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._execute_sync, sql, params)

    async def run_select(self, sql: str, limit: int | None = None) -> list[dict[str, Any]]:
        return await self.run_select_in_schema(sql, None, limit)

    def _run_select_sync(self, sql: str, schema: str) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            psycopg_sql.SQL("SET LOCAL search_path TO {}, public").format(
                                psycopg_sql.Identifier(schema)
                            )
                        )
                        cursor.execute(sql)
                        rows = cursor.fetchall()
                        return [json_safe(dict(row)) for row in rows]
        except Exception as exc:
            if is_db_unreachable(exc):
                raise DatabaseUnavailableError(str(exc)) from exc
            raise

    async def run_select_in_schema(
        self,
        sql: str,
        schema: str | None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        enforce_access_policy(sql)
        capped_sql = normalize_select(sql, limit or settings.max_rows)
        return await asyncio.to_thread(self._run_select_sync, capped_sql, selected_schema)

    def _explain_sync(self, sql: str, schema: str) -> dict[str, Any]:
        try:
            with self._connection() as connection:
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            psycopg_sql.SQL("SET LOCAL search_path TO {}, public").format(
                                psycopg_sql.Identifier(schema)
                            )
                        )
                        cursor.execute(f"EXPLAIN (FORMAT JSON) {sql}")
                        row = cursor.fetchone()
                        if not row:
                            raise ValueError("PostgreSQL returned no EXPLAIN plan.")
                        value = row.get("QUERY PLAN") or row.get("query_plan")
                        if not isinstance(value, list) or not value:
                            raise ValueError("PostgreSQL returned an invalid EXPLAIN plan.")
                        return json_safe(value[0])
        except Exception as exc:
            if is_db_unreachable(exc):
                raise DatabaseUnavailableError(str(exc)) from exc
            raise

    async def explain_select(self, sql: str, schema: str | None) -> dict[str, Any]:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        enforce_access_policy(sql)
        capped_sql = normalize_select(sql, settings.max_rows)
        return await asyncio.to_thread(self._explain_sync, capped_sql, selected_schema)

    async def ping(self) -> dict[str, Any]:
        settings = get_settings()
        try:
            database_name = settings.database.database
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

        versions = await self.execute_internal("SELECT version() AS version")
        schemas = await self.list_schemas()
        counts = await self.execute_internal(
            "SELECT COUNT(*) AS tables FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
            [settings.db_schema],
        )
        return {
            "version": str(versions[0].get("version")) if versions else "unknown",
            "database": database_name,
            "schema": settings.db_schema,
            "schemas": schemas,
            "tables": int(counts[0].get("tables", 0)) if counts else 0,
        }

    async def list_schemas(self) -> list[str]:
        settings = get_settings()
        rows = await self.execute_internal(
            "SELECT schema_name AS name FROM information_schema.schemata "
            "WHERE schema_name = ANY(%s) ORDER BY schema_name",
            [list(settings.allowed_schemas)],
        )
        existing = {str(row["name"]).lower(): str(row["name"]) for row in rows}
        return [existing[name.lower()] for name in settings.allowed_schemas if name.lower() in existing]

    async def list_tables(self, schema: str | None = None) -> list[str]:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        rows = await self.execute_internal(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
            "ORDER BY table_name",
            [selected_schema],
        )
        return [str(row["name"]) for row in rows]

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None


database_service = DatabaseService()
