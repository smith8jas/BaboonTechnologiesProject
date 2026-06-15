import os

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv(find_dotenv())

LLM_MAX_TOKENS = os.getenv("LLM_MAX_TOKENS")

_NODE_DEFAULTS: dict[str, tuple[str, str]] = {
    "router":   ("openai", "gpt-4.1"),
    "plan":     ("openai",    "gpt-4.1"),
    "react":    ("openai",    "gpt-4.1"),
    "response": ("anthropic", "claude-haiku-4-5-20251001"),
    "judge":    ("openai",    "gpt-4o-mini"),
    "scrape":   ("groq",      "llama-3.3-70b-versatile"),
}


def _build_model(provider: str, model: str):
    kwargs: dict = {"model": model, "model_provider": provider, "temperature": 0}
    if LLM_MAX_TOKENS:
        kwargs["max_tokens"] = int(LLM_MAX_TOKENS)
    return init_chat_model(**kwargs)


NODE_PROVIDERS: dict[str, str] = {
    node: os.getenv(f"{node.upper()}_LLM_PROVIDER", default_provider)
    for node, (default_provider, _) in _NODE_DEFAULTS.items()
}

NODE_MODELS = {
    node: _build_model(
        NODE_PROVIDERS[node],
        os.getenv(f"{node.upper()}_LLM_MODEL", default_model),
    )
    for node, (_, default_model) in _NODE_DEFAULTS.items()
}


def get_node_model(node: str):
    return NODE_MODELS[node]


def ask_llm(instruction, **inputs):
    prompt_parts = [instruction]
    for key, value in inputs.items():
        prompt_parts.append(f"{key}: {value}")
    prompt = "\n\n".join(prompt_parts)
    response = NODE_MODELS["response"].invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)
