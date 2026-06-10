from pydantic import BaseModel, Field

from backend.processing.schema import Assumptions, DCFOutput, ValuationInputs


RatioSet = dict[str, dict[str, float | None]]
GrowthSet = dict[str, dict[str, float | None]]


class RatiosResponse(BaseModel):
    ticker: str
    span: int
    liquidity: RatioSet
    solvency: RatioSet
    profitability: RatioSet


class GrowthResponse(BaseModel):
    ticker: str
    span: int
    income_statement: GrowthSet
    balance_sheet: GrowthSet


class DCFResponse(BaseModel):
    ticker: str
    span: int
    year: int
    assumptions: Assumptions
    valuation_inputs: ValuationInputs
    valuation: DCFOutput


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    thread_id: str | None = None
    recursion_limit: int = Field(default=12, ge=3, le=50)


class AgentChatResponse(BaseModel):
    thread_id: str
    session_id: str
    response: str


class UserProfileResponse(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    username: str | None = None
    full_name: str | None = None
    age: int | None = None
    role_title: str | None = None
    company: str | None = None
    bio: str | None = None


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=500)
    username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{3,32}$")
    full_name: str | None = Field(default=None, max_length=120)
    age: int | None = Field(default=None, ge=13, le=130)
    role_title: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=600)


class ChatSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ChatSessionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)


class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    thread_id: str | None = None
    title: str
    created_at: str
    updated_at: str


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: str
