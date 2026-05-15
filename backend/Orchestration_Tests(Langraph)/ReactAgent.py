from llm import CHAT_MODEL #Importing functions from ask_llm file
from langchain.agents import create_agent
from langchain.messages import AnyMessage, SystemMessage, ToolMessage, HumanMessage
from typing_extensions import TypedDict, Annotated
import operator
from typing import Literal
from langgraph.graph import StateGraph, START, END
from datetime import date
from tools import tools
import IPython.display

model_with_tools = CHAT_MODEL.bind_tools(tools)
tools_by_name = {tool.name: tool for tool in tools}


def initialize_agent():
    #Building the node diagram for the agent process
    agent_builder = StateGraph(AgentMemory)

    #Creating nodes
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("tool_node", tool_node)

    #Connecting nodes
    agent_builder.add_edge(START, "llm_call")
    agent_builder.add_edge("tool_node", "llm_call")
    agent_builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END]
        )
    
    agent = agent_builder.compile()
    
    #Displaying the graph
    IPython.display.display(IPython.display.Image(agent.get_graph(xray=True).draw_mermaid_png()))
    
    return(agent)

#Receives user_input and activates agent
def activate_agent(user_input, context, response_type,agent):

    state = {
        "messages": [HumanMessage(content=user_input)],
        "context": context,
        "response_type": response_type,
        "llm_calls": 0,
        "max_llm_calls": 5,
    }
    messages = agent.invoke(state) #This activates the agent with the message
    for m in messages["messages"]:
        m.pretty_print()
    
    return(messages["messages"][-1].content)

#Stores agent memory
class AgentMemory(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    max_llm_calls: int
    context: str
    response_type: str
    #raw_data: Annotated[dict, merge_nested]
    #calculated_data: Annotated[dict, merge_nested]

#Decides whether to call a tool or not
def llm_call(state: AgentMemory):
    system_prompt = f"""
    Agent behavior:
    - This is a test.
    - You are a careful assistant using a ReAct-style workflow.
    - Review the available conversation and tool results before answering.
    - If required information is missing, uncertain, or should be calculated, call the most relevant tool.
    - Call multiple tools in the same step only when they are independent.
    - If a tool call depends on another tool's result, call the prerequisite tool first.
    - If no tool is needed, answer directly.
    - Do not invent data, calculations, or tool results.

    Request configuration:
    - Context: {state["context"]}
    - Response type: {state["response_type"]}
    """
    return {
        "messages": [
            model_with_tools.invoke(
                [SystemMessage(content = system_prompt)] + state["messages"]
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
def should_continue(state: AgentMemory) -> Literal["tool_node", END]:
    messages = state["messages"]
    last_message = messages[-1]
    if state.get("llm_calls", 0) >= state.get("max_llm_calls", 5):
        return END

    if last_message.tool_calls:
        return "tool_node"
    
    return END