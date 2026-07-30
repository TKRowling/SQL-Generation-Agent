from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AIResponseError, AIUnavailableError, ConfigurationError
from app.models.api import ChatMessage


class OllamaClient:
    """Chat client for Ollama. No API key or authorization header is used."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @staticmethod
    def _chat_url() -> str:
        settings = get_settings()
        return f"{settings.ollama_base_url}{settings.ollama_chat_path}"

    async def chat(self, messages: list[ChatMessage]) -> str:
        settings = get_settings()
        if not settings.ollama_configured:
            raise ConfigurationError(
                "Ollama is not configured. Set OLLAMA_BASE_URL and OLLAMA_MODEL."
            )

        payload = {
            "model": settings.ollama_model,
            "messages": [message.model_dump() for message in messages],
            "stream": False,
            "options": {"temperature": settings.ollama_temperature},
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.ollama_timeout_seconds,
                transport=self._transport,
                trust_env=settings.ollama_trust_env,
            ) as client:
                response = await client.post(
                    self._chat_url(),
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(
                f"Ollama network error calling {self._chat_url()}: {exc}"
            ) from exc

        body_text = response.text
        if response.status_code >= 500:
            raise AIUnavailableError(
                f"Ollama HTTP {response.status_code} from {self._chat_url()}: "
                f"{body_text[:300]}"
            )
        if response.status_code >= 400:
            raise AIResponseError(
                f"Ollama HTTP {response.status_code}: {body_text[:300]}"
            )

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise AIResponseError("Ollama returned invalid JSON.") from exc

        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
        if isinstance(data.get("response"), str):
            return str(data["response"])
        raise AIResponseError("Ollama response did not contain text output.")

    async def ping(self) -> dict[str, Any]:
        settings = get_settings()
        tags_url = f"{settings.ollama_base_url}/api/tags"
        try:
            async with httpx.AsyncClient(
                timeout=min(settings.ollama_timeout_seconds, 10),
                transport=self._transport,
                trust_env=settings.ollama_trust_env,
            ) as client:
                response = await client.get(tags_url)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(
                f"Ollama network error calling {tags_url}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise AIUnavailableError(
                f"Ollama HTTP {response.status_code} from {tags_url}: "
                f"{response.text[:300]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise AIResponseError("Ollama tags endpoint returned invalid JSON.") from exc
        models = [
            str(item.get("name") or item.get("model"))
            for item in data.get("models", [])
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        ]
        return {
            "reachable": True,
            "base_url": settings.ollama_base_url,
            "chat_path": settings.ollama_chat_path,
            "model": settings.ollama_model,
            "model_available": settings.ollama_model in models,
            "available_models": models,
        }


ai_client = OllamaClient()
