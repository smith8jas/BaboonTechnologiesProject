"""Agent graph state schema."""

import operator
from typing import Any

from langchain.messages import AnyMessage
from typing_extensions import Annotated, NotRequired, TypedDict

#The Agent State. This is where its short term memory lives
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add] #History of all user, tool and AI messages
    context: str #Context prompt to guide general behavior
    current_year: int #Current year to guide time accuracy
    available_tools: dict[str, list[dict[str, Any]]] #Available tools so it knows what it can do
    router_route: NotRequired[str] #The next step decided by the router node (Can be either plan node or end)
    plan_status: NotRequired[str] #Defined as either (needs_scrape_and_tools, needs_scrape, needs_tools or ready_to_respond)
    react_iterations: NotRequired[int] #Number of times React node has ran
    judge_iterations: NotRequired[int] #Number of times Judge node has ran
    judge_verdict: NotRequired[str] #Verdict from judge node: "end", "revise", or "gather_more"
    judge_react_extensions: NotRequired[int] #Extra react iterations granted by judge when react is at its limit
    forced_response_due_to_recursion: NotRequired[bool] #Boolean that forces response if recursion is being reached
    session_id: NotRequired[str] #DuckDB session key — maps to the per-conversation database file
    data_catalog: NotRequired[dict[str, Any]] #Summary of financial data cache
    scrape_history: NotRequired[Annotated[list[dict[str, Any]], operator.add]] #History of scraped content during conversation
    tool_guidance: NotRequired[str] #Justification for tool use written by plan node and then red by response node
    deep_plan: NotRequired[bool] #Whether the router selected the deep-analysis path for the current request; persists across turns so the next router reads it as previous_depth
    judge_rationale: NotRequired[str] #Critique written by judge_node explaining why it chose its verdict
