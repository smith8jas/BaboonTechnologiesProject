#Chat model
from backend.core.llm import CHAT_MODEL

from langchain.agents import create_agent
from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator

#Tools
from backend.Agent.tools import tools

model_with_tools = CHAT_MODEL.bind_tools(tools)
tools_by_name = {tool.name: tool for tool in tools}

#Stores agent memory (This is the state, different)
class AgentMemory(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    max_llm_calls: int
    context: str
    response_type: str
    #raw_data: Annotated[dict, merge_nested]
    #calculated_data: Annotated[dict, merge_nested]
