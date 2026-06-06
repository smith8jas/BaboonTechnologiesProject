from functools import lru_cache
from uuid import uuid4


@lru_cache(maxsize=1)
def _agent():
    from backend.agent.graph import initialize_agent

    return initialize_agent()


def chat(
    message: str,
    *,
    thread_id: str | None = None,
    recursion_limit: int = 12,
) -> tuple[str, str]:
    """Run one agent turn and return the persisted thread id plus response."""
    text = message.strip()
    if not text:
        raise ValueError("Message cannot be empty.")

    resolved_thread_id = thread_id or f"api-session-{uuid4()}"

    from backend.agent.graph import activate_agent

    response = activate_agent(
        text,
        _agent(),
        thread_id=resolved_thread_id,
        recursion_limit=recursion_limit,
    )
    return resolved_thread_id, response


async def chat_async(
    message: str,
    *,
    thread_id: str | None = None,
    recursion_limit: int = 12,
) -> tuple[str, str]:
    """Run one agent turn asynchronously."""
    text = message.strip()
    if not text:
        raise ValueError("Message cannot be empty.")

    resolved_thread_id = thread_id or f"api-session-{uuid4()}"

    from backend.agent.graph import activate_agent_async

    response = await activate_agent_async(
        text,
        _agent(),
        thread_id=resolved_thread_id,
        recursion_limit=recursion_limit,
    )
    return resolved_thread_id, response


def chat_stream(
    message: str,
    *,
    thread_id: str | None = None,
    recursion_limit: int = 12,
):
    """Run one agent turn and stream the persisted response text chunks."""
    text = message.strip()
    if not text:
        raise ValueError("Message cannot be empty.")

    resolved_thread_id = thread_id or f"api-session-{uuid4()}"

    from backend.agent.graph import activate_agent_stream

    return resolved_thread_id, activate_agent_stream(
        text,
        _agent(),
        thread_id=resolved_thread_id,
        recursion_limit=recursion_limit,
    )


async def chat_stream_async(
    message: str,
    *,
    thread_id: str | None = None,
    recursion_limit: int = 12,
):
    """Run one agent turn and return an async stream of response text chunks."""
    text = message.strip()
    if not text:
        raise ValueError("Message cannot be empty.")

    resolved_thread_id = thread_id or f"api-session-{uuid4()}"

    from backend.agent.graph import activate_agent_stream_async

    return resolved_thread_id, activate_agent_stream_async(
        text,
        _agent(),
        thread_id=resolved_thread_id,
        recursion_limit=recursion_limit,
    )
