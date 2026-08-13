from __future__ import annotations

import pytest

from app.agents.graph import AskMeMultiAgentSystem
from app.models.api import ChatMessage


@pytest.mark.asyncio
async def test_checkpoint_history_is_isolated_by_thread() -> None:
    system = AskMeMultiAgentSystem()

    await system.append_exchange("thread-a", "Question A", "Answer A")
    await system.append_exchange("thread-b", "Question B", "Answer B")

    state_a = await system.graph.aget_state(system._thread_config("thread-a"))
    state_b = await system.graph.aget_state(system._thread_config("thread-b"))

    assert [message.content for message in state_a.values["history"]] == [
        "Question A",
        "Answer A",
    ]
    assert [message.content for message in state_b.values["history"]] == [
        "Question B",
        "Answer B",
    ]


@pytest.mark.asyncio
async def test_reset_deletes_only_selected_thread() -> None:
    system = AskMeMultiAgentSystem()
    await system.append_exchange("thread-a", "Question A", "Answer A")
    await system.append_exchange("thread-b", "Question B", "Answer B")

    await system.reset_thread("thread-a")

    state_a = await system.graph.aget_state(system._thread_config("thread-a"))
    state_b = await system.graph.aget_state(system._thread_config("thread-b"))
    assert not state_a.values
    assert state_b.values["history"][0].content == "Question B"


@pytest.mark.asyncio
async def test_replace_history_keeps_only_edited_prefix() -> None:
    system = AskMeMultiAgentSystem()
    await system.append_exchange("thread-a", "Old question", "Old answer")

    prefix = [
        ChatMessage(role="user", content="First question"),
        ChatMessage(role="assistant", content="First answer"),
    ]
    await system.replace_history("thread-a", prefix)

    state = await system.graph.aget_state(system._thread_config("thread-a"))
    assert [message.content for message in state.values["history"]] == [
        "First question",
        "First answer",
    ]
