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
    schema_max_tables: int = 8
    sql_max_attempts: int = 3

    ai_provider: str = "ollama"

    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_ai_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    cf_ai_temperature: float = 0.1
    cf_ai_timeout_seconds: float = 60

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.1
    ollama_timeout_seconds: float = 120

    db_url: str = ""
    db_user: str = ""
    db_password: str = ""
    db_schema: str = "public"
    db_schemas: str = ""
    db_pool_size: int = 5
    db_connect_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 30000
    db_explain_max_cost: float = 100000
    db_explain_max_rows: int = 1000000
    db_explain_max_joins: int = 8
    restricted_tables: str = "payroll,hr_employees"
    restricted_columns: str = "password,key_secret,ssn,national_id,card_number"
    audit_log_path: str = "logs/audit.jsonl"

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

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"ollama", "cloudflare"}:
            raise ValueError("AI_PROVIDER must be either ollama or cloudflare")
        return provider

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        if not re.match(r"^https?://", url):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return url

    @field_validator("ollama_model")
    @classmethod
    def validate_ollama_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("OLLAMA_MODEL cannot be empty")
        return model

    @field_validator("db_schemas")
    @classmethod
    def validate_db_schemas(cls, value: str) -> str:
        names = [item.strip() for item in value.split(",") if item.strip()]
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
            raise ValueError("DB_SCHEMAS must contain comma-separated unquoted PostgreSQL schema names")
        return ",".join(dict.fromkeys(names))

    @field_validator("schema_max_tables")
    @classmethod
    def validate_schema_max_tables(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("SCHEMA_MAX_TABLES must be between 1 and 50")
        return value

    @field_validator("sql_max_attempts")
    @classmethod
    def validate_sql_max_attempts(cls, value: int) -> int:
        if not 1 <= value <= 3:
            raise ValueError("SQL_MAX_ATTEMPTS must be between 1 and 3")
        return value

    @field_validator("db_explain_max_cost")
    @classmethod
    def validate_explain_cost(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("DB_EXPLAIN_MAX_COST must be greater than zero")
        return value

    @field_validator("db_explain_max_rows", "db_explain_max_joins")
    @classmethod
    def validate_positive_guard_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("EXPLAIN row and join limits must be greater than zero")
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
    def ollama_configured(self) -> bool:
        return bool(self.ollama_base_url and self.ollama_model)

    @property
    def ai_configured(self) -> bool:
        return (
            self.ollama_configured
            if self.ai_provider == "ollama"
            else self.cloudflare_configured
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.db_url)

    @property
    def allowed_schemas(self) -> tuple[str, ...]:
        configured = [item for item in self.db_schemas.split(",") if item]
        return tuple(dict.fromkeys([self.db_schema, *configured]))

    def resolve_schema(self, requested: str | None) -> str:
        if not requested:
            return self.db_schema
        matches = {name.lower(): name for name in self.allowed_schemas}
        resolved = matches.get(requested.strip().lower())
        if resolved is None:
            raise ValueError("The selected schema is not approved.")
        return resolved


@lru_cache
def get_settings() -> Settings:
    return Settings()
