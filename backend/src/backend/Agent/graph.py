from langchain.messages import SystemMessage, ToolMessage, HumanMessage
from typing import Literal
from langgraph.graph import StateGraph, START, END
import IPython.display

from .prompts import agent_behavior, app_context, response_type

from .state import model_with_tools, tools_by_name, AgentMemory #Importing from state file

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
def activate_agent(user_input, context, response_type, agent):

    state = {
        "messages": [HumanMessage(content=user_input)],
        "context": context, #Can replace with app context from prompts
        "response_type": response_type, #Can replace with response type from prompts
        "llm_calls": 0,
        "max_llm_calls": 5,
    }
    messages = agent.invoke(state) #This activates the agent with the message
    for m in messages["messages"]:
        m.pretty_print()
    
    return(messages["messages"][-1].content)

#Decides whether to call a tool or not
def llm_call(state: AgentMemory):
    system_prompt = f"""
    {agent_behavior}

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