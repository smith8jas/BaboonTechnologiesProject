"""Small async PostgREST client for Supabase service-role operations."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from backend.core.config import settings


class SupabaseRestClient:
    """Call Supabase's generated REST API with the backend service role key."""

    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Missing Supabase database configuration: "
                    "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required."
                ),
            )

        self.base_url = settings.supabase_url.rstrip("/")
        self.service_key = settings.supabase_service_role_key

    async def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer

        url = f"{self.base_url}/rest/v1/{table}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Supabase request failed: {exc}",
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Supabase database request failed.",
                    "supabase_status": response.status_code,
                    "supabase_response": response.text,
                },
            )

        if not response.content:
            return None
        return response.json()


def supabase_admin() -> SupabaseRestClient:
    return SupabaseRestClient()
