from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from Generate_Tasks import generate_tasks

from dotenv import load_dotenv, find_dotenv

env_path = find_dotenv()

load_dotenv(env_path)

# Loads environment to configure the chatbot LLM.

LLM_PROVIDER = os.getenv("LLM_PROVIDER")
LLM_MODEL = os.getenv("LLM_MODEL")

# Builds the configured chat model.
def build_chat_model():
    if not LLM_PROVIDER:
        raise RuntimeError("LLM_PROVIDER is not set in backend/Orchestration/.env.")

    if not LLM_MODEL:
        raise RuntimeError("LLM_MODEL is not set in backend/Orchestration/.env.")

    return init_chat_model(
        model=LLM_MODEL,
        model_provider=LLM_PROVIDER,
        temperature=0,
    )


CHAT_MODEL = build_chat_model()


# Chatbot. This is where the user enters an input and receives a response.
def chatbot() -> bool:
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
        generate_tasks(result, sys.modules[__name__],app_context)
    return True


# Function to ask an LLM a question.
def ask_llm(instruction, **inputs):
    prompt_parts = [instruction]
    for key, value in inputs.items():
        prompt_parts.append(f"{key}: {value}")
    prompt = "\n\n".join(prompt_parts)
    response = CHAT_MODEL.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)


if __name__ == "__main__":
    chatbot()