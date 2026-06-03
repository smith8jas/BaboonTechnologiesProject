#Run this to test the agent from the terminal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.Agent.graph import activate_agent, initialize_agent

DEBUG_SAVE_GRAPH = False


# Chatbot. This is where the user enters an input and receives a response.
def chatbot(agent):
    # Prompt the user in a loop and keep each entry as a string.
    message_history = []

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
        if user_input.lower() in {"exit", "quit", "end"}:
            print("Exiting.")
            break
        print(f"You entered: {user_input}")

        result = activate_agent(user_input, agent, message_history)

        print("    ")
        print(message_history)
        print("   ")

if __name__ == "__main__":
    
    agent = initialize_agent(save_graph=DEBUG_SAVE_GRAPH)

    chatbot(agent)
