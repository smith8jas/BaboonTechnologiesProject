from llm import CHAT_MODEL, ask_llm

# Chatbot. This is where the user enters an input and receives a response.
def chatbot():
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

        last_input = user_input
        print(f"You entered: {last_input}")
        try:
            result = last_input
        except RuntimeError as exc:
            print(exc)
            continue
        print(result)

        app_context = "for a financial valuation system"
        #generate_tasks(result, sys.modules[__name__],app_context)
    return True

if __name__ == "__main__":
    chatbot()