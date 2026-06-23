import os

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv(find_dotenv())

LLM_MAX_TOKENS = os.getenv("LLM_MAX_TOKENS")

_NODE_DEFAULTS: dict[str, tuple[str, str]] = {
    # Depth routing is high leverage: false "deep" flags make the whole graph slower/costlier.
    "router":   ("openai",    "gpt-4.1"),

    # Strong instruction following for tool selection, dependency coverage, and scope control.
    "plan":     ("openai",    "gpt-4.1"),

    # Tool-aware reasoning; this node patches gaps and decides whether collection is complete.
    "react":    ("openai",    "gpt-4.1"),

    # Highest-value node: financial synthesis, assumption audit, and grounded interpretation.
    "response": ("anthropic", "claude-sonnet-4-6"),

    # Bad critiques trigger loops, so use a strong judge even though synthesis lives elsewhere.
    "judge":    ("openai",    "gpt-4.1"),

    # External research needs critical query design, but should stay cost-controlled.
    "scrape":   ("openai",    "gpt-5.4-mini"),
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
