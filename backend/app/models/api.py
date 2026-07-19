from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    force_data: bool = False

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        if any(char not in allowed for char in value):
            raise ValueError("session_id may contain only letters, digits, '_' and '-'")
        return value

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class ChatResponse(BaseModel):
    kind: Literal["data", "chat"]
    answer: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    sql: str | None = None


class ResetRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)


class ResetResponse(BaseModel):
    cleared: bool = True


class DatabasePingResponse(BaseModel):
    reachable: bool
    version: str | None = None
    database: str | None = None
    schema_name: str | None = Field(default=None, alias="schema")
    tables: int | None = None
    message: str | None = None


class TablesResponse(BaseModel):
    tables: list[str]
    count: int


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str
    database_configured: bool
    cloudflare_configured: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorBody
