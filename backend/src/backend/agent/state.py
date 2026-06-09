from backend.core.llm import CHAT_MODEL

from langchain.messages import AnyMessage
import operator
from copy import deepcopy
from typing import Any
from typing_extensions import Annotated, NotRequired, TypedDict


def merge_cache(left: dict | None, right: dict | None) -> dict:
    if not left:
        return deepcopy(right or {})
    if not right:
        return deepcopy(left)

    result = deepcopy(left)
    for key, value in right.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_cache(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    context: str
    current_year: int
    available_tools: dict[str, list[dict[str, Any]]]
    router_route: NotRequired[str]
    plan_status: NotRequired[str]
    plan_iterations: NotRequired[int]
    react_iterations: NotRequired[int]
    forced_response_due_to_recursion: NotRequired[bool]
    data_cache: NotRequired[Annotated[dict[str, Any], merge_cache]]
    data_catalog: NotRequired[dict[str, Any]]
    scrape_history: NotRequired[Annotated[list[dict[str, Any]], operator.add]]
    tool_guidance: NotRequired[str]
    previous_depth: NotRequired[bool]
