import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "AskMe Web"


@pytest.mark.asyncio
async def test_agent_info_exposes_langgraph_and_governed_tools() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/info")
    assert response.status_code == 200
    body = response.json()
    assert body["framework"] == "LangGraph"
    assert "sql_agent" in body["nodes"]
    assert "validate_select_sql" in body["tools"]
    assert body["security_owner"] == "deterministic_backend_tools"
