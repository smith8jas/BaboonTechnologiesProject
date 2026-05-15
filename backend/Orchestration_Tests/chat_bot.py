from backend.src.Agent.ReactAgent import activate_agent, initialize_agent
from backend.src.Agent.prompts import app_context, response_type

# Chatbot. This is where the user enters an input and receives a response.
def chatbot(agent):
    # Prompt the user in a loop and keep each entry as a string.
    last_input: str | None = None

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
        user_input
        print(f"You entered: {user_input}")

        #app_context = app_context
        #response_type = response_type
        #generate_tasks(result, sys.modules[__name__],app_context)
        
        print(activate_agent(user_input, app_context, response_type, agent))


    return True

if __name__ == "__main__":
    
    agent = initialize_agent()

    chatbot(agent)
