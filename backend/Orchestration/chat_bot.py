import json

import llm as app_context
from Generate_Tasks import SYSTEM_CONTEXT, generate_tasks
from ReactAgent import activate_agent, initialize_agent

# Chatbot. This is where the user enters an input and receives a response.
def chatbot(agent):
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
        if user_input.lower() in {"exit", "quit"}:
            print("Exiting.")
            break
        print(f"You entered: {user_input}")

        response_type = "State your final answer in an investor thesis to investors format"

        task_list = generate_tasks(user_input, app_context, SYSTEM_CONTEXT)
        print(json.dumps(task_list, indent=2))

        print(activate_agent(user_input, SYSTEM_CONTEXT, response_type, agent, task_list))


    return True

if __name__ == "__main__":
    agent = initialize_agent()
    chatbot(agent)
