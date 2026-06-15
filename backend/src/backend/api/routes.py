"""FastAPI route definitions and transport-level error handling."""

import inspect
import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse

from backend.api.controllers import agent as agent_controller
from backend.api.controllers import chats as chat_controller
from backend.api.controllers import companies as company_controller
from backend.api.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
    ChatSessionUpdateRequest,
    DCFResponse,
    GrowthResponse,
    RatiosResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from backend.auth.dependencies import CurrentUser, get_current_user
from backend.processing.schema import HistoricalFinancials, MarketData, SectorData

router = APIRouter()
companies_router = APIRouter(prefix="/companies", tags=["companies"])
agent_router = APIRouter(prefix="/agent", tags=["agent"])
chat_router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/")
def read_root() -> dict[str, str]:
    """Return a small API identity payload for browsers and smoke tests."""
    return {"message": "Baboon Technologies API"}


@router.get("/health")
def health_check() -> dict[str, str]:
    """Expose a cheap health probe used by the frontend status indicator."""
    return {"status": "ok"}


@companies_router.get(
    "/{ticker}/financials",
    response_model=HistoricalFinancials,
)
def get_company_financials(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=1, le=10),
) -> HistoricalFinancials:
    """Fetch normalized historical financial statements for a ticker."""
    return _call_controller(company_controller.get_company_financials, ticker, span)


@companies_router.get(
    "/{ticker}/market-data",
    response_model=MarketData,
)
def get_company_market_data(
    ticker: str = Path(..., min_length=1, max_length=10),
    include_rfr: bool = Query(default=True),
) -> MarketData:
    """Fetch current market data and, optionally, the risk-free rate."""
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
    """Calculate grouped ratio metrics from historical financial statements."""
    return _call_controller(company_controller.get_company_ratios, ticker, span)


@companies_router.get(
    "/{ticker}/growth",
    response_model=GrowthResponse,
)
def get_company_growth(
    ticker: str = Path(..., min_length=1, max_length=10),
    span: int = Query(default=5, ge=2, le=10),
) -> GrowthResponse:
    """Calculate year-over-year growth rates from historical financial statements."""
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
    """Run the DCF pipeline using company financials, market data, and sector inputs."""
    return _call_controller(company_controller.get_company_dcf, ticker, span, year)


@router.get(
    "/sector-data",
    response_model=SectorData,
    tags=["sector"],
)
def get_sector_data(
    year: int | None = Query(default=None, ge=1900),
) -> SectorData:
    """Fetch sector-wide valuation assumptions for the requested year."""
    return _call_controller(company_controller.get_sector_data, year)


@agent_router.post(
    "/chat",
    response_model=AgentChatResponse,
)
async def chat_with_agent(
    request: AgentChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentChatResponse:
    """Return a complete agent answer after the graph finishes."""
    return await _call_controller_async(agent_controller.chat_with_agent, request, current_user)


@agent_router.post("/chat/stream")
async def stream_chat_with_agent(
    request: AgentChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream agent status, thoughts, and response deltas as newline-delimited JSON."""
    session_id, thread_id, stream = await _call_controller_async(
        agent_controller.stream_chat_with_agent,
        request,
        current_user,
    )

    async def event_stream():
        # Send the resolved thread first so the client can persist continuity
        # before receiving assistant text.
        yield _stream_event({"type": "thread", "thread_id": thread_id, "session_id": session_id})

        try:
            async for event in stream:
                yield _stream_event(event)
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


@router.get("/me", response_model=UserProfileResponse, tags=["auth"])
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the authenticated user's profile."""
    return await _call_controller_async(chat_controller.get_me, current_user)


@router.patch("/me", response_model=UserProfileResponse, tags=["auth"])
async def update_me(
    request: UserProfileUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Update the authenticated user's public profile."""
    return await _call_controller_async(chat_controller.update_me, request, current_user)


@chat_router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ChatSessionResponse]:
    """List the authenticated user's persisted chat sessions."""
    return await _call_controller_async(chat_controller.list_chat_sessions, current_user)


@chat_router.post("/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    request: ChatSessionCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatSessionResponse:
    """Create an empty persisted chat session."""
    return await _call_controller_async(chat_controller.create_chat_session, request, current_user)


@chat_router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    request: ChatSessionUpdateRequest,
    session_id: str = Path(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatSessionResponse:
    """Update session metadata for the authenticated user."""
    return await _call_controller_async(
        chat_controller.update_chat_session,
        session_id,
        request,
        current_user,
    )


@chat_router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str = Path(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    """Delete a chat session and its messages."""
    return await _call_controller_async(chat_controller.delete_chat_session, session_id, current_user)


@chat_router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def list_chat_messages(
    session_id: str = Path(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ChatMessageResponse]:
    """List persisted messages for one authenticated user chat session."""
    return await _call_controller_async(chat_controller.list_chat_messages, session_id, current_user)


def _call_controller(controller: Callable[..., Any], *args: Any) -> Any:
    """Run a sync controller and normalize service exceptions for HTTP clients."""
    try:
        return controller(*args)
    except Exception as exc:
        _raise_service_error(exc)


async def _call_controller_async(controller: Callable[..., Any], *args: Any) -> Any:
    """Run either sync or async controllers behind the same route wrapper."""
    try:
        result = controller(*args)
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception as exc:
        _raise_service_error(exc)


def _raise_service_error(exc: Exception):
    """Translate domain/service exceptions into stable FastAPI error responses."""
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
    """Encode one streaming payload as an NDJSON line."""
    return f"{json.dumps(payload, default=str)}\n"


router.include_router(companies_router)
router.include_router(agent_router)
router.include_router(chat_router)
