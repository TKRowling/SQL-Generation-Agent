from __future__ import annotations

import asyncio
from collections import defaultdict

from app.core.config import get_settings
from app.models.api import ChatMessage


class ConversationStore:
    """Small in-memory history store keyed by browser session ID.

    This preserves the original bot's process-local memory behavior. For a
    multi-worker or horizontally scaled deployment, replace it with Redis or a
    database-backed implementation.
    """

    def __init__(self) -> None:
        self._histories: dict[str, list[ChatMessage]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> list[ChatMessage]:
        async with self._lock:
            return [message.model_copy() for message in self._histories.get(session_id, [])]

    async def append_exchange(self, session_id: str, user_text: str, answer: str) -> None:
        max_messages = get_settings().max_history_turns * 2
        async with self._lock:
            history = self._histories[session_id]
            history.extend(
                [
                    ChatMessage(role="user", content=user_text),
                    ChatMessage(role="assistant", content=answer),
                ]
            )
            if len(history) > max_messages:
                del history[:-max_messages]

    async def reset(self, session_id: str) -> None:
        async with self._lock:
            self._histories.pop(session_id, None)

    async def replace(self, session_id: str, messages: list[ChatMessage]) -> None:
        max_messages = get_settings().max_history_turns * 2
        safe_messages = [
            message.model_copy()
            for message in messages
            if message.role in {"user", "assistant"}
        ][-max_messages:]
        async with self._lock:
            self._histories[session_id] = safe_messages


conversation_store = ConversationStore()
