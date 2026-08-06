from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import ForbiddenQueryError
from app.agents.graph import AskMeMultiAgentSystem
from app.agents.tools import validate_select_sql


class FakeTool:
    def __init__(self, result: Any, calls: list[str], name: str) -> None:
        self.result = result
        self.calls = calls
        self.name = name

    async def ainvoke(self, _payload: dict[str, Any]) -> Any:
        self.calls.append(self.name)
        return self.result


def test_graph_exposes_specialized_agents_and_security_tools() -> None:
    system = AskMeMultiAgentSystem()
    names = set(system.graph.get_graph().nodes)
    assert {
        "supervisor",
        "metadata_agent",
        "schema_agent",
        "sql_agent",
        "validate_tool",
        "explain_tool",
        "execute_tool",
        "verify_tool",
        "correction_agent",
        "reporting_agent",
        "chat_agent",
    }.issubset(names)


@pytest.mark.asyncio
async def test_validation_tool_blocks_restricted_columns_before_catalog_access() -> None:
    with pytest.raises(ForbiddenQueryError):
        await validate_select_sql.ainvoke(
            {"sql": "SELECT password FROM users", "schema_name": "customer360"}
        )


@pytest.mark.asyncio
async def test_sql_route_crosses_all_guarded_tools(monkeypatch) -> None:
    calls: list[str] = []
    sql = "SELECT customer_id FROM customers ORDER BY customer_id LIMIT 10"

    monkeypatch.setattr(
        "app.agents.graph.search_approved_schema",
        FakeTool("customers: customer_id bigint PK", calls, "schema"),
    )
    monkeypatch.setattr(
        "app.agents.graph.get_schema_fingerprint",
        FakeTool("schema-v1", calls, "fingerprint"),
    )
    monkeypatch.setattr(
        "app.agents.graph.validate_select_sql",
        FakeTool(
            {
                "normalized_sql": sql,
                "referenced_tables": ["customers"],
                "projected_columns": ["customer_id"],
                "join_count": 0,
            },
            calls,
            "validate",
        ),
    )
    monkeypatch.setattr(
        "app.agents.graph.explain_query_cost",
        FakeTool(
            {"total_cost": 1.0, "estimated_rows": 1, "node_count": 1},
            calls,
            "explain",
        ),
    )
    monkeypatch.setattr(
        "app.agents.graph.execute_readonly_sql",
        FakeTool([{"customer_id": 1}], calls, "execute"),
    )
    monkeypatch.setattr(
        "app.agents.graph.verify_query_result",
        FakeTool({"passed": True, "issues": []}, calls, "verify"),
    )

    async def no_cached_plan(*_args, **_kwargs):
        return None

    async def remember_plan(*_args, **_kwargs):
        calls.append("cache")

    async def generate_sql(*_args, **_kwargs):
        calls.append("sql_agent")
        return sql

    async def summarize(*_args, **_kwargs):
        calls.append("reporting_agent")
        return "Found one customer."

    async def report(*_args, **_kwargs):
        return ["The query returned 1 row."], None

    monkeypatch.setattr("app.agents.graph.plan_cache.get", no_cached_plan)
    monkeypatch.setattr("app.agents.graph.plan_cache.put", remember_plan)
    monkeypatch.setattr(
        "app.agents.graph.query_agent._generate_sql", generate_sql
    )
    monkeypatch.setattr(
        "app.agents.graph.query_agent._summarize", summarize
    )
    monkeypatch.setattr("app.agents.graph.build_report_with_ai", report)

    result = await AskMeMultiAgentSystem().run(
        question="List the first 10 customers",
        schema_name="customer360",
        history=[],
        system_prompt="Database assistant",
        force_data=True,
    )

    assert result.kind == "data"
    assert result.sql == sql
    assert result.rows == [{"customer_id": 1}]
    assert calls == [
        "schema",
        "fingerprint",
        "sql_agent",
        "validate",
        "explain",
        "execute",
        "verify",
        "cache",
        "reporting_agent",
    ]
