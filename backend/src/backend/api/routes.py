import json
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse

from backend.api.controllers import agent as agent_controller
from backend.api.controllers import companies as company_controller
from backend.api.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    DCFResponse,
    GrowthResponse,
    RatiosResponse,
)
from backend.processing.schema import HistoricalFinancials, MarketData, SectorData

router = APIRouter()
companies_router = APIRouter(prefix="/companies", tags=["companies"])
agent_router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Baboon Technologies API"}


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@companies_router.get(
    "/{ticker}/financials",
    response_model=HistoricalFinancials,
)
def get_company_financials(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=1, le=10),
) -> HistoricalFinancials:
    return _call_controller(company_controller.get_company_financials, ticker, span)


@companies_router.get(
    "/{ticker}/market-data",
    response_model=MarketData,
)
def get_company_market_data(
    ticker: str = Path(..., min_length=1, max_length=10),
    include_rfr: bool = Query(default=True),
) -> MarketData:
    return _call_controller(
        company_controller.get_company_market_data,
        ticker,
        include_rfr,
    )


@companies_router.get(
    "/{ticker}/ratios",
    response_model=RatiosResponse,
)
def get_company_ratios(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=1, le=10),
) -> RatiosResponse:
    return _call_controller(company_controller.get_company_ratios, ticker, span)


@companies_router.get(
    "/{ticker}/growth",
    response_model=GrowthResponse,
)
def get_company_growth(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=2, le=10),
) -> GrowthResponse:
    return _call_controller(company_controller.get_company_growth, ticker, span)


@companies_router.get(
    "/{ticker}/dcf",
    response_model=DCFResponse,
)
def get_company_dcf(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=2, le=10),
    year: int | None = Query(default=None, ge=1900),
) -> DCFResponse:
    return _call_controller(company_controller.get_company_dcf, ticker, span, year)


@router.get(
    "/sector-data",
    response_model=SectorData,
    tags=["sector"],
)
def get_sector_data(
    year: int | None = Query(default=None, ge=1900),
) -> SectorData:
    return _call_controller(company_controller.get_sector_data, year)


@agent_router.post(
    "/chat",
    response_model=AgentChatResponse,
)
def chat_with_agent(request: AgentChatRequest) -> AgentChatResponse:
    return _call_controller(agent_controller.chat_with_agent, request)


@agent_router.post("/chat/stream")
def stream_chat_with_agent(request: AgentChatRequest) -> StreamingResponse:
    thread_id, stream = _call_controller(agent_controller.stream_chat_with_agent, request)

    def event_stream():
        yield _stream_event({"type": "thread", "thread_id": thread_id})

        try:
            for chunk in stream:
                yield _stream_event({"type": "delta", "content": chunk})
            yield _stream_event({"type": "done"})
        except Exception as exc:
            yield _stream_event(
                {
                    "type": "error",
                    "message": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _call_controller(controller: Callable[..., Any], *args: Any) -> Any:
    try:
        return controller(*args)
    except Exception as exc:
        _raise_service_error(exc)


def _raise_service_error(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc

    status_code = (
        status.HTTP_400_BAD_REQUEST
        if isinstance(exc, ValueError)
        else status.HTTP_502_BAD_GATEWAY
    )
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": str(exc),
            "error_type": exc.__class__.__name__,
        },
    ) from exc


def _stream_event(payload: dict[str, Any]) -> str:
    return f"{json.dumps(payload, default=str)}\n"


router.include_router(companies_router)
router.include_router(agent_router)
