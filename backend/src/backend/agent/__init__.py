"""LangGraph financial-analysis agent.

Package layout:
    graph.py      composes nodes and edges into the compiled agent
    runtime.py    activate_agent / activate_agent_async entrypoints
    state.py      AgentState schema and the data_cache merge reducer
    constants.py  recursion and scrape limits shared across the graph
    llm.py        shared LLM invocation with prompt caching
    messages.py   message-history filtering helpers
    prompts.py    node prompts and the data dictionary
    nodes/        one module per graph node
    edges/        one module per conditional edge
    tools/        LangChain tools and the ToolSpec registry
    cache/        per-tool data caches and catalog builders
    streaming/    streaming entrypoints and frontend event translation
    main.py       CLI chatbot entrypoint

The public API below is loaded lazily so importing a submodule (for example
backend.agent.cache from the comparables service) does not build the chat
model or compile the graph.
"""

import importlib

_EXPORTS = {
    "initialize_agent": "backend.agent.graph",
    "activate_agent": "backend.agent.runtime",
    "activate_agent_async": "backend.agent.runtime",
    "activate_agent_stream": "backend.agent.streaming",
    "activate_agent_stream_async": "backend.agent.streaming",
    "activate_agent_stream_events_async": "backend.agent.streaming",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'backend.agent' has no attribute {name!r}")
    return getattr(importlib.import_module(module_path), name)
