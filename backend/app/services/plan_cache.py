from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().casefold().rstrip("?.!")


def question_hash(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


class PlanCache:
    """Persistent validated SQL cache keyed by schema structure and question hash."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()

    def _database_path(self) -> Path:
        path = self._path or Path(get_settings().plan_cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path(), timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS validated_plans (
                schema_name TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                schema_fingerprint TEXT NOT NULL,
                sql TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (schema_name, question_hash, schema_fingerprint)
            )
            """
        )
        return connection

    def _get_sync(self, question: str, schema: str, fingerprint: str) -> str | None:
        with self._lock, self._connect() as connection:
            key = question_hash(question)
            row = connection.execute(
                "SELECT sql FROM validated_plans WHERE schema_name=? "
                "AND question_hash=? AND schema_fingerprint=?",
                (schema, key, fingerprint),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE validated_plans SET last_used_at=?, use_count=use_count+1 "
                "WHERE schema_name=? AND question_hash=? AND schema_fingerprint=?",
                (datetime.now(timezone.utc).isoformat(), schema, key, fingerprint),
            )
            return str(row[0])

    async def get(self, question: str, schema: str, fingerprint: str) -> str | None:
        try:
            return await asyncio.to_thread(self._get_sync, question, schema, fingerprint)
        except (OSError, sqlite3.Error):
            return None

    def _put_sync(self, question: str, schema: str, fingerprint: str, sql: str) -> None:
        settings = get_settings()
        now = datetime.now(timezone.utc).isoformat()
        key = question_hash(question)
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM validated_plans WHERE schema_name=? AND question_hash=? "
                "AND schema_fingerprint<>?",
                (schema, key, fingerprint),
            )
            connection.execute(
                """
                INSERT INTO validated_plans
                    (schema_name, question_hash, schema_fingerprint, sql,
                     created_at, last_used_at, use_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(schema_name, question_hash, schema_fingerprint)
                DO UPDATE SET sql=excluded.sql, last_used_at=excluded.last_used_at,
                              use_count=validated_plans.use_count+1
                """,
                (schema, key, fingerprint, sql, now, now),
            )
            connection.execute(
                "DELETE FROM validated_plans WHERE rowid IN ("
                "SELECT rowid FROM validated_plans ORDER BY last_used_at DESC "
                "LIMIT -1 OFFSET ?)",
                (settings.plan_cache_max_entries,),
            )

    async def put(self, question: str, schema: str, fingerprint: str, sql: str) -> None:
        try:
            await asyncio.to_thread(self._put_sync, question, schema, fingerprint, sql)
        except (OSError, sqlite3.Error):
            return

    def _delete_sync(self, question: str, schema: str, fingerprint: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM validated_plans WHERE schema_name=? AND question_hash=? "
                "AND schema_fingerprint=?",
                (schema, question_hash(question), fingerprint),
            )

    async def delete(self, question: str, schema: str, fingerprint: str) -> None:
        try:
            await asyncio.to_thread(self._delete_sync, question, schema, fingerprint)
        except (OSError, sqlite3.Error):
            return


plan_cache = PlanCache()
