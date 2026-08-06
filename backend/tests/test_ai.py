import json

import httpx
import pytest

from app.core.config import Settings
from app.models.api import ChatMessage
from app.services.ai import WorkersAIClient


@pytest.mark.asyncio
async def test_workers_ai_sends_bearer_token_and_extracts_response(monkeypatch) -> None:
    settings = Settings(cf_account_id="account", cf_api_token="token", _env_file=None)
    monkeypatch.setattr("app.services.ai.get_settings", lambda: settings)
    async def handler(request: httpx.Request) -> httpx.Response:
        assert "/accounts/" in request.url.path
        assert request.headers["authorization"].startswith("Bearer ")
        payload = json.loads(request.content)
        assert payload["messages"][0]["content"] == "Generate SQL"
        return httpx.Response(
            200,
            json={"success": True, "result": {"response": "SELECT 1"}},
        )

    result = await WorkersAIClient(
        transport=httpx.MockTransport(handler)
    ).chat([ChatMessage(role="user", content="Generate SQL")])
    assert result == "SELECT 1"


@pytest.mark.asyncio
async def test_workers_ai_rejects_missing_text_output(monkeypatch) -> None:
    settings = Settings(cf_account_id="account", cf_api_token="token", _env_file=None)
    monkeypatch.setattr("app.services.ai.get_settings", lambda: settings)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"success": True, "result": {}})
    )
    with pytest.raises(Exception, match="did not contain text output"):
        await WorkersAIClient(transport=transport).chat(
            [ChatMessage(role="user", content="Generate SQL")]
        )


@pytest.mark.asyncio
async def test_specialized_clients_select_their_configured_models(monkeypatch) -> None:
    settings = Settings(
        cf_account_id="account",
        cf_api_token="token",
        cf_sql_model="@cf/test/sql-model",
        cf_knowledge_model="@cf/test/knowledge-model",
        _env_file=None,
    )
    monkeypatch.setattr("app.services.ai.get_settings", lambda: settings)
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"success": True, "result": {"response": "ok"}},
        )

    transport = httpx.MockTransport(handler)
    await WorkersAIClient(transport=transport, model_role="sql").chat(
        [ChatMessage(role="user", content="Generate SQL")]
    )
    await WorkersAIClient(transport=transport, model_role="knowledge").chat(
        [ChatMessage(role="user", content="Explain a table")]
    )

    assert requested_paths[0].endswith("/@cf/test/sql-model")
    assert requested_paths[1].endswith("/@cf/test/knowledge-model")
