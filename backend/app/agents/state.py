from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.models.api import ChartSpec, ChatMessage


class AgentState(TypedDict, total=False):
    """Small shared state passed between LangGraph nodes."""

    question: str
    schema_name: str
    history: list[ChatMessage]
    system_prompt: str
    force_data: bool
    route: Literal["metadata", "sql", "chat"]
    schema_context: str
    schema_fingerprint: str
    sql: str
    normalized_sql: str
    rows: list[dict[str, Any]]
    answer: str
    kind: Literal["data", "chat"]
    insights: list[str]
    chart: ChartSpec | None
    attempt: int
    error: str
    cached_plan: bool
    attempted_sql: list[str]
    fatal_error: bool
    exception: Exception


@dataclass
class MultiAgentAnswer:
    """Stable result returned by the graph to the FastAPI layer."""

    kind: Literal["data", "chat"]
    answer: str
    rows: list[dict[str, Any]]
    sql: str | None = None
    insights: list[str] | None = None
    chart: ChartSpec | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)
