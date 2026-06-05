from backend.core.llm import CHAT_MODEL

from langchain.messages import AnyMessage
import operator
from typing import Any
from typing_extensions import Annotated, NotRequired, TypedDict


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    context: str
    current_year: int
    available_tools: list[dict[str, Any]]
    router_route: NotRequired[str]
    plan_status: NotRequired[str]
