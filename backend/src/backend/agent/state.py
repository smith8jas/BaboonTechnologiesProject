"""Agent graph state schema and the data_cache merge reducer."""

import logging
import operator
from copy import deepcopy
from typing import Any

from langchain.messages import AnyMessage
from typing_extensions import Annotated, NotRequired, TypedDict

logger = logging.getLogger(__name__)


def _merge_lists(left: list, right: list) -> list:
    """Union of two lists, deduplicated and sorted where possible."""
    seen = []
    for item in left + right:
        if item not in seen:
            seen.append(item)
    try:
        seen.sort()
    except TypeError:
        pass
    return seen


def merge_cache(left: dict | None, right: dict | None) -> dict:
    if not left:
        return deepcopy(right or {})
    if not right:
        return deepcopy(left)

    result = deepcopy(left)
    for key, value in right.items():
        existing = result.get(key)

        # Take right: key is new or left is empty
        if key not in result or existing is None:
            result[key] = deepcopy(value)

        # Take left: right is empty
        elif value is None:
            pass

        # Merge both
        elif isinstance(existing, dict) and isinstance(value, dict):
            result[key] = merge_cache(existing, value)
        elif isinstance(existing, list) or isinstance(value, list):
            left_items = existing if isinstance(existing, list) else [existing]
            right_items = value if isinstance(value, list) else [value]
            result[key] = _merge_lists(left_items, right_items)
        else:
            if existing != value:
                logger.warning("Cache conflict on '%s': %r vs %r — keeping right", key, existing, value)
            result[key] = deepcopy(value)

    return result

#The Agent State. This is where its short term memory lives
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add] #History of all user, tool and AI messages
    context: str #Context prompt to guide general behavior
    current_year: int #Current year to guide time accuracy
    available_tools: dict[str, list[dict[str, Any]]] #Available tools so it knows what it can do
    router_route: NotRequired[str] #The next step decided by the router node (Can be either plan node or end)
    plan_status: NotRequired[str] #Defined as either (needs_scrape_and_tools, needs_scrape, needs_tools or ready_to_respond)
    react_iterations: NotRequired[int] #Number of times React node has ran
    forced_response_due_to_recursion: NotRequired[bool] #Boolean that forces response if recursion is being reached
    data_cache: NotRequired[Annotated[dict[str, Any], merge_cache]] #Short term cache for financial data
    data_catalog: NotRequired[dict[str, Any]] #Summary of financial data cache
    scrape_history: NotRequired[Annotated[list[dict[str, Any]], operator.add]] #History of scraped content during conversation
    tool_guidance: NotRequired[str] #Justification for tool use written by plan node and then red by response node
    previous_depth: NotRequired[bool] #Boolean that decides required depth of analysis and response (ser by router node)
