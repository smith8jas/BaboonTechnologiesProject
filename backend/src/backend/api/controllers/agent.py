from uuid import uuid4

from backend.api.schemas import AgentChatRequest, AgentChatResponse
from backend.auth.dependencies import CurrentUser
from backend.repositories import chats
from backend.services import agent_service


async def chat_with_agent(
    request: AgentChatRequest,
    current_user: CurrentUser,
) -> AgentChatResponse:
    session, thread_id = await _resolve_session(request, current_user)
    await chats.create_message(
        current_user.id,
        session["id"],
        role="user",
        content=request.message,
        metadata={"thread_id": thread_id},
    )

    thread_id, response = await agent_service.chat_async(
        request.message,
        thread_id=thread_id,
        recursion_limit=request.recursion_limit,
    )
    await chats.create_message(
        current_user.id,
        session["id"],
        role="assistant",
        content=response,
        metadata={"thread_id": thread_id},
    )
    await chats.update_session(
        current_user.id,
        session["id"],
        {"thread_id": thread_id, "title": session["title"]},
    )
    return AgentChatResponse(
        thread_id=thread_id,
        session_id=session["id"],
        response=response,
    )


async def stream_chat_with_agent(
    request: AgentChatRequest,
    current_user: CurrentUser,
):
    session, thread_id = await _resolve_session(request, current_user)
    await chats.create_message(
        current_user.id,
        session["id"],
        role="user",
        content=request.message,
        metadata={"thread_id": thread_id},
    )
    _, stream = await agent_service.chat_stream_events_async(
        request.message,
        thread_id=thread_id,
        recursion_limit=request.recursion_limit,
    )

    async def persisted_stream():
        chunks: list[str] = []
        async for event in stream:
            if event.get("type") == "delta":
                chunks.append(str(event.get("content") or ""))
            yield event

        content = "".join(chunks).strip()
        if content:
            await chats.create_message(
                current_user.id,
                session["id"],
                role="assistant",
                content=content,
                metadata={"thread_id": thread_id, "streamed": True},
            )
            await chats.update_session(
                current_user.id,
                session["id"],
                {"thread_id": thread_id, "title": session["title"]},
            )

    return session["id"], thread_id, persisted_stream()


async def _resolve_session(
    request: AgentChatRequest,
    current_user: CurrentUser,
) -> tuple[dict, str]:
    if request.session_id:
        session = await chats.require_session(current_user.id, request.session_id)
        thread_id = request.thread_id or session.get("thread_id") or f"api-session-{uuid4()}"
        if session.get("thread_id") != thread_id:
            session = await chats.update_session(
                current_user.id,
                session["id"],
                {"thread_id": thread_id},
            )
        return session, thread_id

    if request.thread_id:
        existing = await chats.get_session_by_thread_id(current_user.id, request.thread_id)
        if existing:
            return existing, request.thread_id

    thread_id = request.thread_id or f"api-session-{uuid4()}"
    session = await chats.create_session(
        current_user.id,
        title=chats.title_from_message(request.message),
        thread_id=thread_id,
    )
    return session, thread_id
