#Run this to test the agent from the terminal
#cd backend
#uv run python src/backend/agent/main.py
import logging
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent.graph import initialize_agent
from backend.agent.runtime import activate_agent_async

from uuid import uuid4

DEBUG_NODE_UPDATES = True
DEBUG_AGENT_STATE = True


# Chatbot. This is where the user enters an input and receives a response.
def chatbot(agent):
    """This function is a loop. It prompts the user to enter an input in the terminal and generates a response
    from the agent. If the user wants to end, they type exit. This is for backend testing."""

    #Assigns a random value to the thread_id in format (cli-session-#########)
    thread_id = f"cli-session-{uuid4()}"

    #Infinite loop
    while True:
        #Chat bot prompts user to enter a message. The user's input is stripped from the external spaces (rightmost and leftmost)
        try:
            user_input: str = input("Enter a message: ").strip()
        #Exceptions that break the loop in case there was a problem initiating the loop
        except KeyboardInterrupt:
            #print("\nExiting.")
            break
        except EOFError:
            #print("\nExiting.")
            break

        #If the user types "exit" the loop breaks
        if user_input.lower() == "exit":
            print("Exiting.")
            break

        #Prints what the user typed in the terminal (for debugging)
        print(f"You entered: {user_input}")

        #Function that gives the agent the user's input and returns the agent's response response.
        response = asyncio.run(
            activate_agent_async(
                user_input, 
                agent, 
                thread_id=thread_id, 
                debug_updates=DEBUG_NODE_UPDATES,
                )
            )

        print("  ")
        print("Agent response to user:  ")
        print(response)
        print("  ")

        if DEBUG_AGENT_STATE:
            print_agent_state(agent, thread_id)

        print("  ")

#Prints agent state
def print_agent_state(agent, thread_id):
      config = {
          "configurable": {"thread_id": thread_id},
      }
      state = agent.get_state(config)
      messages = state.values.get("messages", [])

      print("\nCurrent checkpointed messages:")
      print("  ")
      for i, message in enumerate(messages, 1):
          role = message.type
          content = getattr(message, "content", "")
          print(f"{i}. {role}: {content[:300]}")

def save_graph_png(agent):
    output_path = Path(__file__).parent / "graph.png"
    png_bytes = agent.get_graph().draw_mermaid_png()
    output_path.write_bytes(png_bytes)
    print(f"Graph saved to {output_path}")


if __name__ == "__main__":

    #Backend test starts here

    logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

    #Function that sets up the nodes and edges of the agent
    agent = initialize_agent()

    #Function that creates a png of the compiled agent and saves it in a folder
    save_graph_png(agent)

    #Function that receives the compiled agent and initiates a loop to simulate a chatbot in the terminal
    #with the agent
    chatbot(agent)
