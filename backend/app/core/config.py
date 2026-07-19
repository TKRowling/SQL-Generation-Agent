from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    host: str
    port: int = 5432
    database: str
    user: str
    password: str
    sslmode: str | None = None


def parse_db_url(raw: str | None, env_user: str = "", env_password: str = "") -> DatabaseConfig:
    """Parse JDBC or standard PostgreSQL URLs into connection properties."""
    if not raw:
        raise ValueError("DB_URL is not set")

    normalized = raw.removeprefix("jdbc:") if raw.lower().startswith("jdbc:") else raw
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"postgresql", "postgres"}:
        raise ValueError(
            "DB_URL must use postgresql://, postgres://, or jdbc:postgresql://"
        )
    if not parsed.hostname:
        raise ValueError("DB_URL does not contain a database host")

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("DB_URL does not contain a database name")

    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", [None])[0]

    return DatabaseConfig(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=unquote(database),
        user=unquote(parsed.username or "") or env_user,
        password=unquote(parsed.password or "") or env_password,
        sslmode=sslmode,
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AskMe Web"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    askme_api_key: str = ""
    expose_sql: bool = False
    max_rows: int = 50
    max_history_turns: int = 8
    schema_cache_seconds: int = 600

    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_ai_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cf_ai_temperature: float = 0.1
    cf_ai_timeout_seconds: float = 60

    db_url: str = ""
    db_user: str = ""
    db_password: str = ""
    db_schema: str = "public"
    db_pool_size: int = 5
    db_connect_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 30000

    bot_system_prompt: str = (
        "You are AskMe, a concise and helpful assistant for the connected PostgreSQL "
        "database. Answer clearly. If you are unsure, say so."
    )

    @field_validator("db_schema")
    @classmethod
    def validate_db_schema(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("DB_SCHEMA must be a valid unquoted PostgreSQL schema name")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database(self) -> DatabaseConfig:
        return parse_db_url(self.db_url, self.db_user, self.db_password)

    @property
    def cloudflare_configured(self) -> bool:
        return bool(self.cf_account_id and self.cf_api_token)

    @property
    def database_configured(self) -> bool:
        return bool(self.db_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
