"""Helpers for reading and filtering the LangChain message history in state."""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)


def latest_human_message_content(state) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.content

    return ""


def latest_tool_calls(state) -> list[dict]:
    for message in reversed(state.get("messages", [])):
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            return tool_calls

    return []


def current_tool_block(state) -> list:
    """Messages from the last AI tool-call message to end of messages (active tool exchange)."""
    messages = state.get("messages", [])
    last_tool_call_ai_index = None
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            last_tool_call_ai_index = i
    if last_tool_call_ai_index is None:
        return []
    return messages[last_tool_call_ai_index:]


def last_human_from_dialogue(state):
    """Most recent HumanMessage from dialogue."""
    for m in reversed(state.get("dialogue", [])):
        if isinstance(m, HumanMessage):
            return m
    return None


def messages_for_llm(state) -> list:
    messages = state.get("messages", [])
    last_tool_call_ai_index = None
    last_final_ai_index = None

    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue
        if getattr(message, "tool_calls", None):
            last_tool_call_ai_index = index
        else:
            last_final_ai_index = index

    include_active_tool_block = (
        last_tool_call_ai_index is not None
        and (
            last_final_ai_index is None
            or last_tool_call_ai_index > last_final_ai_index
        )
    )

    filtered = []
    for index, message in enumerate(messages):
        if include_active_tool_block and index >= last_tool_call_ai_index:
            filtered.append(message)
            continue

        if getattr(message, "type", None) == "tool":
            continue
        if getattr(message, "tool_calls", None):
            continue

        filtered.append(message)

    return filtered



def log_tool_calls(label: str, message: AIMessage) -> None:
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        logger.debug("%s: %s", label, json.dumps(tool_calls, indent=2, default=str))
