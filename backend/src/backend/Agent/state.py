#Chat model
from backend.core.llm import CHAT_MODEL


from langchain.messages import AnyMessage
from typing import Any
from typing_extensions import TypedDict, Annotated
import operator

#Tools
from backend.services.financials import financial_tools
from backend.services.growth import growth_tools
from backend.services.ratio import ratio_tools

tools = [
    *financial_tools,
    *growth_tools,
    *ratio_tools,
]

model_with_tools = CHAT_MODEL.bind_tools(tools)
tools_by_name = {tool.name: tool for tool in tools}

#Stores agent memory (This is the state, different)
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    max_llm_calls: int
    context: str
    current_year: int
    available_tools: list[dict[str, Any]]
    tool_plan: list[dict[str, Any]]
    tool_results: dict[str, list[dict[str, Any]]]
    route: str
    #raw_data: Annotated[dict, merge_nested]
    #calculated_data: Annotated[dict, merge_nested]
