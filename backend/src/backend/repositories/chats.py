"""User-scoped chat persistence using Supabase PostgREST."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from backend.db.supabase import supabase_admin


def title_from_message(message: str) -> str:
    """Create a compact session title from the user's first prompt."""
    text = " ".join(message.strip().split())
    if not text:
        return "New research thread"
    return text if len(text) <= 42 else f"{text[:39]}..."


async def get_profile(user_id: str) -> dict[str, Any] | None:
    rows = await supabase_admin().request(
        "GET",
        "profiles",
        params={"id": f"eq.{user_id}", "select": "*", "limit": "1"},
    )
    return _first(rows)


async def update_profile(
    user_id: str,
    *,
    email: str | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Update the public profile row, creating it if the auth trigger missed it."""
    clean_changes = {key: _blank_to_none(value) for key, value in changes.items()}
    existing = await get_profile(user_id)

    if existing:
        rows = await supabase_admin().request(
            "PATCH",
            "profiles",
            params={"id": f"eq.{user_id}"},
            json_body=clean_changes,
            prefer="return=representation",
        )
        return _require_first(rows, "Profile not found.")

    rows = await supabase_admin().request(
        "POST",
        "profiles",
        json_body={
            "id": user_id,
            "email": email,
            **clean_changes,
        },
        prefer="return=representation",
    )
    return _require_first(rows, "Could not create profile.")


async def list_sessions(user_id: str) -> list[dict[str, Any]]:
    return await supabase_admin().request(
        "GET",
        "chat_sessions",
        params={
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "updated_at.desc",
        },
    )


async def create_session(
    user_id: str,
    *,
    title: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    rows = await supabase_admin().request(
        "POST",
        "chat_sessions",
        json_body={
            "user_id": user_id,
            "title": title or "New research thread",
            "thread_id": thread_id,
        },
        prefer="return=representation",
    )
    return _require_first(rows, "Could not create chat session.")


async def get_session(user_id: str, session_id: str) -> dict[str, Any] | None:
    rows = await supabase_admin().request(
        "GET",
        "chat_sessions",
        params={
            "id": f"eq.{session_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        },
    )
    return _first(rows)


async def get_session_by_thread_id(user_id: str, thread_id: str) -> dict[str, Any] | None:
    rows = await supabase_admin().request(
        "GET",
        "chat_sessions",
        params={
            "thread_id": f"eq.{thread_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        },
    )
    return _first(rows)


async def update_session(
    user_id: str,
    session_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    rows = await supabase_admin().request(
        "PATCH",
        "chat_sessions",
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        json_body=changes,
        prefer="return=representation",
    )
    return _require_first(rows, "Chat session not found.")


async def delete_session(user_id: str, session_id: str) -> None:
    await supabase_admin().request(
        "DELETE",
        "chat_sessions",
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
    )


async def list_messages(user_id: str, session_id: str) -> list[dict[str, Any]]:
    await require_session(user_id, session_id)
    return await supabase_admin().request(
        "GET",
        "chat_messages",
        params={
            "session_id": f"eq.{session_id}",
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.asc",
        },
    )


async def create_message(
    user_id: str,
    session_id: str,
    *,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await require_session(user_id, session_id)
    rows = await supabase_admin().request(
        "POST",
        "chat_messages",
        json_body={
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
        },
        prefer="return=representation",
    )
    return _require_first(rows, "Could not create chat message.")


async def require_session(user_id: str, session_id: str) -> dict[str, Any]:
    session = await get_session(user_id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )
    return session


def _first(rows: Any) -> dict[str, Any] | None:
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


def _require_first(rows: Any, message: str) -> dict[str, Any]:
    first = _first(rows)
    if not first:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    return first


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value
