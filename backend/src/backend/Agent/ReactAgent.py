
#Replace with file that calls chat model API (Currently importing test files)
#from backend.Orchestration_Tests.llm import CHAT_MODEL 

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage

#Replace with files with tools (Currently importing test files)
#from backend.Orchestration_Tests.tools import tools 

from .prompts import React_Agent_Prompt



#Since this is a premade agent, the state and graph is managed by langchain

#Agent is turned on and is given the tools
def initialize_agent():
    return create_agent(
        model=CHAT_MODEL,
        tools=tools,
        system_prompt= React_Agent_Prompt
    )

#Agent receives input and starts process
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
