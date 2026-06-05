from datetime import date

from backend.api.schemas import DCFResponse, GrowthResponse, RatiosResponse
from backend.processing.schema import HistoricalFinancials, MarketData, SectorData


def get_company_financials(ticker: str, span: int) -> HistoricalFinancials:
    from backend.services import financials

    return financials.get_financials(_ticker(ticker), span)


def get_company_market_data(ticker: str, include_rfr: bool) -> MarketData:
    from backend.services import financials

    return financials.get_market_data(_ticker(ticker), include_rfr)


def get_company_ratios(ticker: str, span: int) -> RatiosResponse:
    from backend.services import financials, ratio

    symbol = _ticker(ticker)
    hf = financials.get_financials(symbol, span)
    return RatiosResponse(
        ticker=symbol,
        span=span,
        liquidity=ratio.get_liquidity_ratios(hf),
        solvency=ratio.get_solvency_ratios(hf),
        profitability=ratio.get_profitability_ratios(hf),
    )


def get_company_growth(ticker: str, span: int) -> GrowthResponse:
    from backend.services import financials, growth

    symbol = _ticker(ticker)
    hf = financials.get_financials(symbol, span)
    return GrowthResponse(
        ticker=symbol,
        span=span,
        income_statement=growth.get_income_statement_growth_rates(hf),
        balance_sheet=growth.get_balance_sheet_growth_rates(hf),
    )


def get_company_dcf(
    ticker: str,
    span: int,
    year: int | None = None,
) -> DCFResponse:
    from backend.services import dcf_engine, financials

    symbol = _ticker(ticker)
    resolved_year = year or date.today().year
    hf = financials.get_financials(symbol, span)
    md = financials.get_market_data(symbol)
    sd = financials.get_sector_data(resolved_year)
    assumptions = dcf_engine.build_assumptions(hf, md, sd)
    valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd)
    valuation = dcf_engine.run_dcf(hf, valuation_inputs, assumptions)

    return DCFResponse(
        ticker=symbol,
        span=span,
        year=resolved_year,
        assumptions=assumptions,
        valuation_inputs=valuation_inputs,
        valuation=valuation,
    )


def get_sector_data(year: int | None = None) -> SectorData:
    from backend.services import financials

    resolved_year = year or date.today().year
    return financials.get_sector_data(resolved_year)


def _ticker(ticker: str) -> str:
    return ticker.strip().upper()
