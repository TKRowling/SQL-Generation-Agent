import logging
from types import SimpleNamespace

import pytest

from app.agents.debug import traced_node


@pytest.mark.asyncio
async def test_agent_debug_logs_are_useful_and_redacted(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.agents.debug.get_settings",
        lambda: SimpleNamespace(agent_debug=True),
    )

    async def node(_state):
        return {"route": "sql", "rows": [{"secret": "do-not-log"}]}

    with caplog.at_level(logging.INFO, logger="askme.agents"):
        result = await traced_node("sql_agent", node)(
            {
                "question": "Show private customer records",
                "sql": "SELECT customer_id FROM customers",
                "schema_name": "customer360",
                "attempt": 1,
            }
        )

    logs = caplog.text
    assert result["route"] == "sql"
    assert "agent_node_start node=sql_agent" in logs
    assert "agent_node_end node=sql_agent" in logs
    assert "question_hash=" in logs
    assert "sql_hash=" in logs
    assert "Show private customer records" not in logs
    assert "SELECT customer_id" not in logs
    assert "do-not-log" not in logs
