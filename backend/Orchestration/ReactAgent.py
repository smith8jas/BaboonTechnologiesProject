from llm import CHAT_MODEL
from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage
from tools import tools
from datetime import date


def initialize_agent():
    return create_agent(
        model=CHAT_MODEL,
        tools=tools,
        system_prompt="""
        Agent behavior:
        - This is a test.
        - You are a careful assistant using a ReAct-style workflow.
        - Review the available conversation and tool results before answering.
        - If required information is missing, uncertain, or should be calculated, call the most relevant tool.
        - If no tool is needed, answer directly.
        - Call multiple tools in the same step only when they are independent.
        - If a tool call depends on another tool's result, call the prerequisite tool first.
        - Do not invent data, calculations, or tool results.
        """
    )


def activate_agent(user_input, context, response_type, agent):
      result = agent.invoke({
          "messages": [
              SystemMessage(content=f"""
              Request configuration:
              - Context: {context}
              - Response type: {response_type}
              """),
              HumanMessage(content=user_input),
          ]
      })

      for message in result["messages"]:
          message.pretty_print()

      return result["messages"][-1].content


"""Data structure proposal for storing numeric data:
dict[entity, dict[metric,dict[date, value]]]
Repeat for many entities, each entity with many metrics, each metric with many dates"""
raw_data: dict[str, dict[str, dict[date, float]]] = {}
calculated_data: dict[str, dict[str, dict[date, float]]] = {}

"""Function to update numeric data ...
Work in progress"""
def merge_nested(existing: dict, new:dict):
    for entity, metrics in new.items():
        if entity not in existing:
            existing[entity] = {}
            for metric, dates in metrics.items():
                if metric not in existing[entity]:
                    existing[entity][metric] = {}
                existing[entity][metric].update(dates)
    return existing
