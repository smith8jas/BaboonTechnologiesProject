"""Service layer: pull, normalize, and validate financial data."""

from collections import OrderedDict
from datetime import date
from threading import Lock

from backend.adapters.edgar import Edgar
from backend.adapters.yahoo_finance import fetch_yahoo_market
from backend.adapters.fred import fetch_risk_free_rate
from backend.adapters.damodaran import fetch_equity_risk_premium
from backend.processing.xbrl_map import (
    PS_MAPPINGS,
    IS_MAPPINGS,
    BS_MAPPINGS,
    CFS_MAPPINGS,
    map_all_periods,
)
from backend.processing.schema import (
    MarketData,
    SectorData,
    PerShare,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    CompanyMetadata,
    FinancialPeriod,
    HistoricalFinancials,
)

_FINANCIALS_CACHE_MAXSIZE = 128
_financials_cache: OrderedDict[tuple[str, int], HistoricalFinancials] = OrderedDict()
_financials_cache_lock = Lock()
_financials_key_locks: dict[tuple[str, int], Lock] = {}


def get_financials(ticker: str, span: int = 5) -> HistoricalFinancials:
    """
    Pull, normalize, and validate historical financials for a ticker.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        span: Number of annual fiscal periods (10-K filings) to retrieve.

    Returns:
        HistoricalFinancials with metadata and per-period statements.
    """
    company = Edgar(ticker)
    raw_metadata = company.metadata()
    financials = company.fetch_all(span)

    mapped_ps = map_all_periods(financials["income_statement"], PS_MAPPINGS)
    mapped_is = map_all_periods(financials["income_statement"], IS_MAPPINGS)
    mapped_bs = map_all_periods(financials["balance_sheet"], BS_MAPPINGS)
    mapped_cf = map_all_periods(financials["cash_flow"], CFS_MAPPINGS)

    all_period_keys = sorted(
        set(mapped_is) | set(mapped_bs) | set(mapped_cf) | set(mapped_ps)
    )

    periods = [
        FinancialPeriod(
            period_end=date.fromisoformat(p),
            income_statement=IncomeStatement(**mapped_is.get(p, {})),
            balance_sheet=BalanceSheet(**mapped_bs.get(p, {})),
            cash_flow=CashFlowStatement(**mapped_cf.get(p, {})),
            per_share=PerShare(**mapped_ps.get(p, {})),
        )
        for p in all_period_keys
    ]

    return HistoricalFinancials(
        ticker=ticker,
        metadata=CompanyMetadata(**raw_metadata),
        periods=periods,
    )


def get_cached_financials(ticker: str, span: int = 5) -> HistoricalFinancials:
    """Return historical financials from an in-process cache when available."""
    key = (ticker.strip().upper(), int(span))

    with _financials_cache_lock:
        cached = _financials_cache.get(key)
        if cached is not None:
            _financials_cache.move_to_end(key)
            return cached

        # Use a per-key lock so a burst of identical requests only performs one
        # external Edgar fetch while unrelated tickers can still proceed.
        key_lock = _financials_key_locks.setdefault(key, Lock())

    with key_lock:
        with _financials_cache_lock:
            cached = _financials_cache.get(key)
            if cached is not None:
                _financials_cache.move_to_end(key)
                return cached

        result = get_financials(key[0], key[1])

        with _financials_cache_lock:
            _financials_cache[key] = result
            _financials_cache.move_to_end(key)
            while len(_financials_cache) > _FINANCIALS_CACHE_MAXSIZE:
                _financials_cache.popitem(last=False)

        return result


def get_market_data(ticker: str, include_rfr: bool = True) -> MarketData:
    """
    Pull market data (price, beta, shares, market cap) and optional risk-free rate.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, fetch FRED DGS10 risk-free rate.

    Returns:
        MarketData with current market values.
    """
    yahoo = fetch_yahoo_market(ticker)
    rfr = fetch_risk_free_rate() if include_rfr else None

    return MarketData(
        current_price=yahoo["current_price"],
        beta=yahoo["beta"],
        shares_outstanding=yahoo["shares_outstanding"],
        market_cap=yahoo["market_cap"],
        risk_free_rate=rfr,
    )


def get_sector_data(year) -> SectorData:
    """Pull sector-level financial assumptions for a given year."""
    return SectorData(
        equity_risk_premium=fetch_equity_risk_premium(year)
    )
