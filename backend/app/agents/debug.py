from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.state import AgentState
from app.core.config import get_settings


logger = logging.getLogger("askme.agents")
AgentNode = Callable[[AgentState], Awaitable[dict[str, Any]]]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10] if value else "none"


def traced_node(name: str, node: AgentNode) -> AgentNode:
    """Add safe timing logs without exposing questions, SQL, or result rows."""

    async def run(state: AgentState) -> dict[str, Any]:
        if not get_settings().agent_debug:
            return await node(state)

        started = time.perf_counter()
        logger.info(
            "agent_node_start node=%s schema=%s attempt=%s question_hash=%s sql_hash=%s",
            name,
            state.get("schema_name", "none"),
            state.get("attempt", 0),
            _hash(state.get("question", "")),
            _hash(state.get("sql", "")),
        )
        try:
            result = await node(state)
        except Exception:
            logger.exception("agent_node_failed node=%s", name)
            raise
        logger.info(
            "agent_node_end node=%s duration_ms=%s route=%s has_error=%s row_count=%s",
            name,
            round((time.perf_counter() - started) * 1000),
            result.get("route", state.get("route", "none")),
            bool(result.get("error")),
            len(result.get("rows", [])) if "rows" in result else "unchanged",
        )
        return result

    run.__name__ = name
    return run
