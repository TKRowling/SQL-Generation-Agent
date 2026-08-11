from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import AIResponseError, AIUnavailableError, ConfigurationError
from app.models.api import ChatMessage


class AIClient(Protocol):
    """Provider-neutral interface used by the rest of the application."""

    async def chat(self, messages: list[ChatMessage]) -> str:
        """Return one text response for an ordered chat-message list."""
        ...


class WorkersAIClient:
    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        model_role: str = "default",
    ) -> None:
        self._transport = transport
        self._model_role = model_role

    def _model(self, settings: Any) -> str:
        if self._model_role == "sql":
            return settings.sql_model
        if self._model_role == "knowledge":
            return settings.knowledge_model
        return settings.cf_ai_model

    async def chat(self, messages: list[ChatMessage]) -> str:
        settings = get_settings()
        if not settings.cloudflare_configured:
            raise ConfigurationError(
                "Cloudflare Workers AI is not configured. Set CF_ACCOUNT_ID and CF_API_TOKEN."
            )

        model = self._model(settings)
        url = (
            f"{self.BASE_URL}/accounts/{settings.cf_account_id}/ai/run/"
            f"{model}"
        )
        payload = {
            "messages": [message.model_dump() for message in messages],
            "temperature": settings.cf_ai_temperature,
        }
        headers = {
            "Authorization": f"Bearer {settings.cf_api_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.cf_ai_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(f"Workers AI network error: {exc}") from exc

        body_text = response.text
        if response.status_code == 429 or response.status_code >= 500:
            raise AIUnavailableError(
                f"Workers AI HTTP {response.status_code}: {body_text[:300]}"
            )
        if response.status_code >= 400:
            raise AIResponseError(
                f"Workers AI HTTP {response.status_code}: {body_text[:300]}"
            )
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise AIResponseError("Workers AI returned invalid JSON.") from exc

        if data.get("success") is False:
            errors = str(data.get("errors", []))
            if any(token in errors.lower() for token in ("rate limit", "allocation", "neurons")):
                raise AIUnavailableError(f"Workers AI error: {errors}")
            raise AIResponseError(f"Workers AI error: {errors}")

        result = data.get("result")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("response", "text", "output_text"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        raise AIResponseError("Workers AI response did not contain text output.")


class OllamaAIClient:
    """Client for Ollama's native, non-streaming /api/chat endpoint."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        model_role: str = "default",
    ) -> None:
        self._transport = transport
        self._model_role = model_role

    def _model(self, settings: Any) -> str:
        if self._model_role == "sql":
            return settings.ollama_sql_model_name
        if self._model_role == "knowledge":
            return settings.ollama_knowledge_model_name
        return settings.ollama_model

    async def chat(self, messages: list[ChatMessage]) -> str:
        settings = get_settings()
        if not settings.ollama_configured:
            raise ConfigurationError(
                "Ollama is not configured. Set OLLAMA_BASE_URL and OLLAMA_MODEL."
            )

        payload = {
            "model": self._model(settings),
            "messages": [message.model_dump() for message in messages],
            "stream": False,
            "options": {"temperature": settings.ollama_ai_temperature},
        }
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        try:
            async with httpx.AsyncClient(
                timeout=settings.ollama_ai_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(url, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(f"Ollama network error: {exc}") from exc

        body_text = response.text
        if response.status_code == 429 or response.status_code >= 500:
            raise AIUnavailableError(
                f"Ollama HTTP {response.status_code}: {body_text[:300]}"
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
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content
        raise AIResponseError("Ollama response did not contain message content.")


def create_ai_client(
    model_role: str = "default",
    transport: httpx.AsyncBaseTransport | None = None,
) -> AIClient:
    """Create a client for the provider selected by AI_PROVIDER."""
    provider = get_settings().ai_provider
    if provider == "cloudflare":
        return WorkersAIClient(transport=transport, model_role=model_role)
    if provider == "ollama":
        return OllamaAIClient(transport=transport, model_role=model_role)
    raise ConfigurationError(f"Unsupported AI provider: {provider}")


sql_ai_client = create_ai_client(model_role="sql")
knowledge_ai_client = create_ai_client(model_role="knowledge")
# Backwards-compatible default for callers that do not need a specialized role.
ai_client = knowledge_ai_client
