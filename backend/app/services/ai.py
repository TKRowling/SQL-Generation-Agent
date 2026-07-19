from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AIResponseError, AIUnavailableError, ConfigurationError
from app.models.api import ChatMessage


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


workers_ai = WorkersAIClient()
