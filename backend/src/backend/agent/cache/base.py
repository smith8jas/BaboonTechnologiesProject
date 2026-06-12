"""Cache skeletons and shared helpers used by every tool cache."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.processing.schema import HistoricalFinancials

from .schema import (
    CACHE_CALCULATED,
    CACHE_COMPANIES,
    CACHE_FINANCIALS,
    CACHE_GLOBAL,
    CACHE_SEARCHED,
    CACHE_SECTOR_DATA_BY_YEAR,
)


EMPTY_DATA_CACHE = {
    CACHE_COMPANIES: {},
    CACHE_GLOBAL: {
        CACHE_SECTOR_DATA_BY_YEAR: {},
    },
}

EMPTY_DATA_CATALOG = {
    CACHE_COMPANIES: [],
    CACHE_GLOBAL: {
        "sector_data_years": [],
    },
}


def empty_data_cache() -> dict[str, Any]:
    """Return a fresh mutable cache with the expected top-level keys."""
    return deepcopy(EMPTY_DATA_CACHE)


def empty_data_catalog() -> dict[str, Any]:
    """Return a fresh catalog skeleton used for prompt-visible data summaries."""
    return deepcopy(EMPTY_DATA_CATALOG)


def state_cache(state: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized deep copy of the graph state's data cache."""
    cache = deepcopy(state.get("data_cache") or empty_data_cache())
    cache.setdefault(CACHE_COMPANIES, {})
    cache.setdefault(CACHE_GLOBAL, {}).setdefault(CACHE_SECTOR_DATA_BY_YEAR, {})
    return cache


def tool_content(payload: Any) -> str:
    """Serialize tool payloads into JSON strings for LangChain ToolMessage content."""
    if isinstance(payload, BaseModel):
        return json.dumps(CacheHelpers.dump_model(payload), default=str)
    return json.dumps(payload, default=str)


def fiscal_year_key(year: Any) -> str:
    """Normalize fiscal-year labels ("FY2023", 2023, " 2023 ") to a plain string key."""
    return str(year).strip().upper().removeprefix("FY")


def financials_coverage(hf: HistoricalFinancials, span: int) -> dict[str, Any]:
    """Describe which fiscal periods a HistoricalFinancials payload covers."""
    return {
        "fiscal_years": [fiscal_year_key(p.fiscal_year) for p in hf.periods],
        "period_ends": [p.period_end.isoformat() for p in hf.periods],
        "max_span": max(int(span), len(hf.periods)),
    }


class CacheHelpers:
    @staticmethod
    def company(cache: dict[str, Any], ticker: str) -> dict[str, Any]:
        key = CacheHelpers.ticker(ticker)
        companies = cache.setdefault(CACHE_COMPANIES, {})
        return companies.setdefault(
            key,
            {
                "ticker": key,
                "name": None,
                CACHE_SEARCHED: {},
                CACHE_CALCULATED: {},
            },
        )

    @staticmethod
    def calculated_entry(
        payload: dict[str, Any],
        hf: HistoricalFinancials,
        depends_on: list[str],
    ) -> dict[str, Any]:
        coverage = financials_coverage(hf, len(hf.periods))
        return {
            "payload": payload,
            "coverage": coverage,
            "depends_on": depends_on,
            "source_fingerprint": {CACHE_FINANCIALS: coverage},
            "last_updated": CacheHelpers.now(),
        }

    @staticmethod
    def coverage_satisfies(coverage: dict[str, Any], span: int) -> bool:
        return int(coverage.get("max_span") or 0) >= int(span)

    @staticmethod
    def catalog_leaf_map(source: dict[str, Any]) -> dict[str, Any]:
        return {
            key: {
                "available": True,
                "fiscal_years": value.get("coverage", {}).get("fiscal_years", []),
            }
            for key, value in source.items()
        }

    @staticmethod
    def dump_model(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(mode="json")

    @staticmethod
    def ticker(ticker: str) -> str:
        return str(ticker).strip().upper()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
