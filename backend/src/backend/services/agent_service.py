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
