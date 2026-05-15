#Used to Call LLM provider API

import os

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model

load_dotenv(find_dotenv())

env_path = find_dotenv()

load_dotenv(env_path)

#Loads environment to configure the chatbot LLM.

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

# Function to ask an LLM a question.
def ask_llm(instruction, **inputs):
    prompt_parts = [instruction]
    for key, value in inputs.items():
        prompt_parts.append(f"{key}: {value}")
    prompt = "\n\n".join(prompt_parts)
    response = CHAT_MODEL.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)