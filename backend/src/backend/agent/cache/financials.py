"""Cache for historical financial statements keyed by ticker and fiscal year."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.processing.schema import HistoricalFinancials
from backend.services import financials as financials_service

from .base import CacheHelpers, financials_coverage, fiscal_year_key
from .schema import CACHE_FINANCIALS, CACHE_SEARCHED


class FinancialsCache:
    CACHE_KEY = CACHE_FINANCIALS
    BUCKET = CACHE_SEARCHED

    @staticmethod
    def get_or_fetch(
        cache: dict[str, Any],
        ticker: str,
        span: int = 5,
        fiscal_years: list[int] | None = None,
    ) -> tuple[HistoricalFinancials, bool]:
        if fiscal_years:
            if FinancialsCache._has_fiscal_years(cache, ticker, fiscal_years):
                return FinancialsCache._from_cache_by_years(cache, ticker, fiscal_years), True
            needed_span = max(span, date.today().year - min(int(y) for y in fiscal_years) + 2)
            hf = financials_service.get_cached_financials(CacheHelpers.ticker(ticker), int(needed_span))
            FinancialsCache._store(cache, hf, int(needed_span))
            return FinancialsCache._filter_by_years(hf, fiscal_years), False

        if FinancialsCache._has(cache, ticker, span):
            return FinancialsCache._from_cache(cache, ticker, span), True

        hf = financials_service.get_cached_financials(CacheHelpers.ticker(ticker), int(span))
        FinancialsCache._store(cache, hf, int(span))
        return hf, False

    @staticmethod
    def _store(cache: dict[str, Any], hf: HistoricalFinancials, span: int) -> None:
        company = CacheHelpers.company(cache, hf.ticker)
        company["name"] = hf.metadata.name
        financials_cache = company[CACHE_SEARCHED].setdefault(
            CACHE_FINANCIALS,
            {
                "payload_type": "HistoricalFinancials",
                "metadata": {},
                "periods_by_fiscal_year": {},
                "coverage": {},
                "last_updated": None,
            },
        )
        financials_cache["metadata"] = CacheHelpers.dump_model(hf.metadata)
        for period in hf.periods:
            key = fiscal_year_key(period.fiscal_year or period.period_end.year)
            financials_cache["periods_by_fiscal_year"][key] = CacheHelpers.dump_model(period)
        financials_cache["coverage"] = FinancialsCache.coverage(hf, span)
        financials_cache["last_updated"] = CacheHelpers.now()

    @staticmethod
    def _has(cache: dict[str, Any], ticker: str, span: int) -> bool:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
        return bool(entry and CacheHelpers.coverage_satisfies(entry.get("coverage", {}), span))

    @staticmethod
    def _from_cache(cache: dict[str, Any], ticker: str, span: int) -> HistoricalFinancials:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
        periods = [
            value
            for _, value in sorted(
                entry["periods_by_fiscal_year"].items(),
                key=lambda item: item[1].get("period_end", ""),
            )
        ]
        if span:
            periods = periods[-int(span):]
        return HistoricalFinancials.model_validate(
            {
                "ticker": CacheHelpers.ticker(ticker),
                "metadata": entry["metadata"],
                "periods": periods,
            }
        )

    @staticmethod
    def _has_fiscal_years(cache: dict[str, Any], ticker: str, fiscal_years: list[int]) -> bool:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
        if not entry:
            return False
        cached = {
            fiscal_year_key(y)
            for y in entry.get("coverage", {}).get("fiscal_years", [])
        }
        return all(fiscal_year_key(y) in cached for y in fiscal_years)

    @staticmethod
    def _from_cache_by_years(
        cache: dict[str, Any],
        ticker: str,
        fiscal_years: list[int],
    ) -> HistoricalFinancials:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
        years_set = {fiscal_year_key(y) for y in fiscal_years}
        periods = sorted(
            [v for k, v in entry["periods_by_fiscal_year"].items()
             if fiscal_year_key(k) in years_set],
            key=lambda p: p.get("period_end", ""),
        )
        return HistoricalFinancials.model_validate(
            {"ticker": CacheHelpers.ticker(ticker), "metadata": entry["metadata"], "periods": periods}
        )

    @staticmethod
    def _filter_by_years(hf: HistoricalFinancials, fiscal_years: list[int]) -> HistoricalFinancials:
        years_set = {fiscal_year_key(y) for y in fiscal_years}
        filtered = [p for p in hf.periods if fiscal_year_key(p.fiscal_year) in years_set]
        return HistoricalFinancials.model_validate(
            {
                "ticker": hf.ticker,
                "metadata": hf.metadata.model_dump(mode="json"),
                "periods": [p.model_dump(mode="json") for p in filtered],
            }
        )

    @staticmethod
    def coverage(hf: HistoricalFinancials, span: int) -> dict[str, Any]:
        return financials_coverage(hf, span)

    @staticmethod
    def _summary(ticker: str, coverage: dict[str, Any]) -> str:
        years = coverage.get("fiscal_years", [])
        if not years:
            return f"Historical financial statements for {ticker} are available."
        return f"Historical financial statements for {ticker} are available for {years[0]}-{years[-1]}."

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_FINANCIALS)
        if not entry:
            return None
        coverage = entry.get("coverage", {})
        return {
            "available": True,
            "fiscal_years": coverage.get("fiscal_years", []),
            "period_ends": coverage.get("period_ends", []),
            "max_span": coverage.get("max_span"),
            "summary": FinancialsCache._summary(company_cache.get("ticker", ""), coverage),
        }

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_FINANCIALS)
        if not entry:
            return None
        return {
            "metadata": entry.get("metadata"),
            "periods": sorted(
                entry.get("periods_by_fiscal_year", {}).values(),
                key=lambda p: p.get("period_end", ""),
            ),
        }
