import json

import httpx
import pytest

from app.models.api import ChatMessage
from app.services.ai import OllamaClient


@pytest.mark.asyncio
async def test_ollama_chat_uses_local_api_without_authorization_header() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["messages"][0]["content"] == "Generate SQL"
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "SELECT 1"}},
        )

    client = OllamaClient(transport=httpx.MockTransport(handler))
    result = await client.chat(
        [ChatMessage(role="user", content="Generate SQL")]
    )
    assert result == "SELECT 1"


@pytest.mark.asyncio
async def test_ollama_rejects_missing_text_output() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"message": {"role": "assistant"}})
    )
    client = OllamaClient(transport=transport)
    with pytest.raises(Exception, match="did not contain text output"):
        await client.chat([ChatMessage(role="user", content="Generate SQL")])
