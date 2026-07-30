from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AIResponseError, AIUnavailableError, ConfigurationError
from app.models.api import ChatMessage


class OllamaClient:
    """Chat client for an Ollama service. Ollama does not require an API key."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

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
            ) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(f"Ollama network error: {exc}") from exc

        body_text = response.text
        if response.status_code >= 500:
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
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
        if isinstance(data.get("response"), str):
            return str(data["response"])
        raise AIResponseError("Ollama response did not contain text output.")


class WorkersAIClient:
    BASE_URL = "https://api.cloudflare.com/client/v4"

    async def chat(self, messages: list[ChatMessage]) -> str:
        settings = get_settings()
        if not settings.cloudflare_configured:
            raise ConfigurationError(
                "Cloudflare Workers AI is not configured. Set CF_ACCOUNT_ID and CF_API_TOKEN."
            )

        url = (
            f"{self.BASE_URL}/accounts/{settings.cf_account_id}/ai/run/"
            f"{settings.cf_ai_model}"
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
            async with httpx.AsyncClient(timeout=settings.cf_ai_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIUnavailableError(f"Workers AI network error: {exc}") from exc

        body_text = response.text
        if response.status_code == 429 or response.status_code >= 500:
            raise AIUnavailableError(
                f"Workers AI HTTP {response.status_code}: {body_text[:300]}"
            )
        if response.status_code >= 400:
            raise AIResponseError(f"Workers AI HTTP {response.status_code}: {body_text[:300]}")

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise AIResponseError("Workers AI returned invalid JSON.") from exc

        if data.get("success") is False:
            errors = data.get("errors", [])
            text = str(errors)
            if any(token in text.lower() for token in ("rate limit", "allocation", "neurons")):
                raise AIUnavailableError(f"Workers AI error: {text}")
            raise AIResponseError(f"Workers AI error: {text}")

        result = data.get("result")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("response", "text", "output_text"):
                value = result.get(key)
                if isinstance(value, str):
                    return value

        raise AIResponseError("Workers AI response did not contain text output.")


class AIClient:
    def __init__(
        self,
        ollama: OllamaClient | None = None,
        cloudflare: WorkersAIClient | None = None,
    ) -> None:
        self.ollama = ollama or OllamaClient()
        self.cloudflare = cloudflare or WorkersAIClient()

    async def chat(self, messages: list[ChatMessage]) -> str:
        provider = get_settings().ai_provider
        if provider == "ollama":
            return await self.ollama.chat(messages)
        if provider == "cloudflare":
            return await self.cloudflare.chat(messages)
        raise ConfigurationError(f"Unsupported AI provider: {provider}")


# Compatibility name retained so query and reporting services need no provider logic.
workers_ai = AIClient()
