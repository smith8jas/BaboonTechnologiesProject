#Run this to test the agent from the terminal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent.graph import activate_agent, initialize_agent

from uuid import uuid4

DEBUG_NODE_UPDATES = True
DEBUG_AGENT_STATE = True


# Chatbot. This is where the user enters an input and receives a response.
def chatbot(agent):
    # Prompt the user in a loop and keep each entry as a string.
    thread_id = f"cli-session-{uuid4()}"

    while True:
        try:
            user_input: str = input("Enter a message: ").strip()
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except EOFError:
            print("\nExiting.")
            break

        # Chatbot starts here. The lines above only handle exit conditions.
        if user_input.lower() == "exit":
            print("Exiting.")
            break
        print(f"You entered: {user_input}")
        
        response = activate_agent(user_input, agent, thread_id=thread_id, debug_updates=DEBUG_NODE_UPDATES,
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

    agent = initialize_agent()
    save_graph_png(agent)

    chatbot(agent)
