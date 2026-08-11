import json

import httpx
import pytest

from app.core.config import Settings
from app.models.api import ChatMessage
from app.services.ai import OllamaAIClient, WorkersAIClient, create_ai_client


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


@pytest.mark.asyncio
async def test_ollama_sends_non_streaming_chat_and_extracts_content(monkeypatch) -> None:
    settings = Settings(
        ai_provider="ollama",
        ollama_base_url="http://ollama.test:11434/",
        ollama_model="llama3.1:8b",
        ollama_sql_model="qwen2.5-coder:14b",
        _env_file=None,
    )
    monkeypatch.setattr("app.services.ai.get_settings", lambda: settings)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.test:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen2.5-coder:14b"
        assert payload["stream"] is False
        assert payload["messages"][0]["content"] == "Generate SQL"
        return httpx.Response(200, json={"message": {"content": "SELECT 1"}})

    result = await OllamaAIClient(
        transport=httpx.MockTransport(handler), model_role="sql"
    ).chat([ChatMessage(role="user", content="Generate SQL")])

    assert result == "SELECT 1"


@pytest.mark.asyncio
async def test_ollama_rejects_missing_message_content(monkeypatch) -> None:
    settings = Settings(ai_provider="ollama", _env_file=None)
    monkeypatch.setattr("app.services.ai.get_settings", lambda: settings)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"message": {}})
    )

    with pytest.raises(Exception, match="did not contain message content"):
        await OllamaAIClient(transport=transport).chat(
            [ChatMessage(role="user", content="Hello")]
        )


def test_factory_selects_configured_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.get_settings",
        lambda: Settings(ai_provider="cloudflare", _env_file=None),
    )
    assert isinstance(create_ai_client("sql"), WorkersAIClient)

    monkeypatch.setattr(
        "app.services.ai.get_settings",
        lambda: Settings(ai_provider="ollama", _env_file=None),
    )
    assert isinstance(create_ai_client("sql"), OllamaAIClient)
