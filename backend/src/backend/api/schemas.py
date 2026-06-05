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
    thread_id: str | None = None
    recursion_limit: int = Field(default=12, ge=3, le=50)


class AgentChatResponse(BaseModel):
    thread_id: str
    response: str
