from llm import CHAT_MODEL, ask_llm #Importing functions from ask_llm file

from langchain.agents import create_agent

from langchain.messages import AnyMessage, SystemMessage, ToolMessage, HumanMessage
from typing_extensions import TypedDict, Annotated

import operator
from typing import Literal

from langgraph.graph import StateGraph, MessagesState, START, END

from datetime import date

from langchain_core.tools import tool
from tools import tools

import IPython.display

model_with_tools = CHAT_MODEL.bind_tools(tools)
tools_by_name = {tool.name: tool for tool in tools}

#Receives user_input and activates agent
def activate_agent(user_input):

    #Building the node diagram for the agent process
    agent_builder = StateGraph(MessagesState)
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("tool_node", tool_node)
    agent_builder.add_edge(START, "llm_call")
    agent_builder.add_conditional_edges(
        "llm_call",
        should_continue,
        ["tool_node", END]
        )
    
    agent = agent_builder.compile()

    #Displaying the graph
    IPython.display.display(IPython.display.Image(agent.get_graph(xray=True).draw_mermaid_png()))

    messages = [HumanMessage(content = user_input)] #List of inputs
    messages = agent.invoke({"messages": messages}) #This activates the agent with the message
    for m in messages["messages"]:
        m.pretty_print()
    
    return(messages["messages"][-1].content)

#Stores agent memory
class AgentMemory(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    #raw_data: Annotated[dict, merge_nested]
    #calculated_data: Annotated[dict, merge_nested]
    llm_calls: int

raw_data: dict[str, dict[str, dict[date, float]]] = {}
calculated_data: dict[str, dict[str, dict[date, float]]] = {}

def merge_nested(existing: dict, new:dict):
    for entity, metrics in new.items():
        if entity not in existing:
            existing[entity] = {}
            for metric, dates in metrics.items():
                if metric not in existing[entity]:
                    existing[entity][metric] = {}
                existing[entity][metric].update(dates)
    return existing

#Decides whether to call a tool or not
def llm_call(state:dict):
    return {
        "messages": [
            model_with_tools.invoke(
                [
                    SystemMessage(
                        content= "You are a test bot, call the right tool if available" 
                    )
                ]
                + state["messages"]
            )
        ],
        "llm_calls": state.get('llm_calls', 0) + 1
    }

#Calls tool
def tool_node(state: dict):
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        return {"messages": result}


#Decides whether to call more tools or end the process    
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"
    
    return END

print("Done")