"""Controllers for authenticated user profile and chat persistence."""

from backend.api.schemas import (
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
    ChatSessionUpdateRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from backend.auth.dependencies import CurrentUser
from backend.repositories import chats


async def get_me(current_user: CurrentUser) -> UserProfileResponse:
    profile = await chats.get_profile(current_user.id)
    return _profile_response(current_user, profile)


async def update_me(
    request: UserProfileUpdateRequest,
    current_user: CurrentUser,
) -> UserProfileResponse:
    profile = await chats.update_profile(
        current_user.id,
        email=current_user.email,
        changes=request.model_dump(exclude_unset=True),
    )
    return _profile_response(current_user, profile)


def _profile_response(
    current_user: CurrentUser,
    profile: dict | None,
) -> UserProfileResponse:
    return UserProfileResponse(
        id=current_user.id,
        email=(profile or {}).get("email") or current_user.email,
        display_name=(profile or {}).get("display_name"),
        avatar_url=(profile or {}).get("avatar_url"),
        username=(profile or {}).get("username"),
        full_name=(profile or {}).get("full_name"),
        age=(profile or {}).get("age"),
        role_title=(profile or {}).get("role_title"),
        company=(profile or {}).get("company"),
        bio=(profile or {}).get("bio"),
    )


async def list_chat_sessions(current_user: CurrentUser) -> list[ChatSessionResponse]:
    rows = await chats.list_sessions(current_user.id)
    return [ChatSessionResponse(**row) for row in rows]


async def create_chat_session(
    request: ChatSessionCreateRequest,
    current_user: CurrentUser,
) -> ChatSessionResponse:
    row = await chats.create_session(current_user.id, title=request.title)
    return ChatSessionResponse(**row)


async def update_chat_session(
    session_id: str,
    request: ChatSessionUpdateRequest,
    current_user: CurrentUser,
) -> ChatSessionResponse:
    changes = {}
    if request.title is not None:
        changes["title"] = request.title
    row = await chats.update_session(current_user.id, session_id, changes)
    return ChatSessionResponse(**row)


async def delete_chat_session(session_id: str, current_user: CurrentUser) -> dict[str, bool]:
    await chats.delete_session(current_user.id, session_id)
    return {"ok": True}


async def list_chat_messages(
    session_id: str,
    current_user: CurrentUser,
) -> list[ChatMessageResponse]:
    rows = await chats.list_messages(current_user.id, session_id)
    return [ChatMessageResponse(**row) for row in rows]
