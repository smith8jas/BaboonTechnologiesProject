"""Shared helpers used across the agent cache layer."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def tool_content(payload: Any) -> str:
    """Serialize tool payloads into JSON strings for LangChain ToolMessage content."""
    if isinstance(payload, BaseModel):
        return json.dumps(payload.model_dump(mode="json"), default=str)
    return json.dumps(payload, default=str)


class CacheMissError(RuntimeError):
    """Raised when a calculation cache requires data not yet in DuckDB.

    Signals that the corresponding research tool was not called before this
    calculation tool — a planning error that should surface explicitly rather
    than silently trigger an external fetch.
    """


class CacheHelpers:
    @staticmethod
    def ticker(ticker: str) -> str:
        return str(ticker).strip().upper()

    @staticmethod
    def dump_model(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(mode="json")
