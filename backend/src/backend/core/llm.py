import os
import re

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


# ── Provider/model capability registry ──────────────────────────────────────
# Providers format requests and responses differently; these tables centralize
# every compatibility decision so invoke paths stay branch-free.

# Models that reject sampling parameters outright (400 on temperature).
# Anthropic removed temperature/top_p/top_k on Opus 4.7+, Sonnet 5+, Fable, and
# Mythos; OpenAI reasoning models (o-series, gpt-5 family) accept only defaults.
_NO_TEMPERATURE_PATTERNS = [
    r"claude-opus-4-[7-9]",
    r"claude-(opus|sonnet|haiku)-[5-9]",
    r"claude-fable",
    r"claude-mythos",
    r"gpt-5",
    r"\bo[134](?:-mini|-pro)?\b",
]


def supports_temperature(model: str) -> bool:
    name = str(model).lower()
    return not any(re.search(p, name) for p in _NO_TEMPERATURE_PATTERNS)


# Ordered with_structured_output method preference per provider. Each ladder
# ends in "prompt_json" — the universal fallback implemented in agent/llm.py
# (plain completion + JSON instruction + Pydantic validation with one retry),
# which is what makes providers without native structured output usable.
STRUCTURED_METHOD_LADDERS: dict[str, tuple[str, ...]] = {
    "openai":          ("function_calling", "json_mode", "prompt_json"),
    "anthropic":       ("function_calling", "prompt_json"),
    "xai":             ("function_calling", "json_mode", "prompt_json"),
    "bedrock":         ("function_calling", "prompt_json"),
    "bedrock_converse": ("function_calling", "prompt_json"),
    "groq":            ("function_calling", "json_mode", "prompt_json"),
    "mistralai":       ("function_calling", "json_mode", "prompt_json"),
    "cohere":          ("function_calling", "prompt_json"),
    "google_genai":    ("function_calling", "json_mode", "prompt_json"),
    "google_vertexai": ("function_calling", "json_mode", "prompt_json"),
    "fireworks":       ("function_calling", "json_mode", "prompt_json"),
    "together":        ("function_calling", "json_mode", "prompt_json"),
    "ollama":          ("json_schema", "prompt_json"),
    "huggingface":     ("prompt_json",),
}
DEFAULT_STRUCTURED_LADDER: tuple[str, ...] = ("function_calling", "prompt_json")


def structured_method_ladder(provider: str) -> tuple[str, ...]:
    return STRUCTURED_METHOD_LADDERS.get(provider, DEFAULT_STRUCTURED_LADDER)


# Providers whose system messages accept Anthropic-style content-block lists
# (required for cache_control breakpoints). Everyone else gets a plain string.
SYSTEM_BLOCK_PROVIDERS = {"anthropic"}

# Providers that reject system-only conversations and consecutive same-role
# messages (strict human/AI alternation).
STRICT_ROLE_PROVIDERS = {"google_genai", "google_vertexai"}


def message_text(message) -> str:
    """Normalize message content to plain text across providers.

    OpenAI-style models return content as str; Anthropic-style models can
    return a list of blocks (text/thinking/tool_use). Accepts a message object
    or raw content.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _build_model(provider: str, model: str):
    kwargs: dict = {"model": model, "model_provider": provider}
    if supports_temperature(model):
        kwargs["temperature"] = 0
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
    return message_text(response)
