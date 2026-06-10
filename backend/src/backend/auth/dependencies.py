"""FastAPI dependencies for Supabase Auth access tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from fastapi import Header, HTTPException, status

from backend.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user identity resolved from a Supabase access token."""

    id: str
    email: str | None
    access_token: str
    raw_user: dict[str, Any]


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Verify the Bearer token with Supabase Auth and return the current user."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token.",
        )

    _require_supabase_auth_config()
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not verify Supabase session: {exc}",
        ) from exc

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase session.",
        )

    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase session did not include a user id.",
        )

    return CurrentUser(
        id=user_id,
        email=payload.get("email"),
        access_token=token,
        raw_user=payload,
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _require_supabase_auth_config() -> None:
    missing = [
        name
        for name, value in {
            "SUPABASE_URL": settings.supabase_url,
            "SUPABASE_ANON_KEY": settings.supabase_anon_key,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing Supabase auth configuration: {', '.join(missing)}",
        )
