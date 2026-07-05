"""Unit tests for the cross-provider LLM compatibility layer.

Covers:
- supports_temperature model patterns (new Anthropic/OpenAI models reject it)
- message_text normalization (str vs content-block lists)
- build_system_prompt format per provider (blocks vs plain string)
- _prepare_messages (empty-conversation guard, strict-role merging)
- _extract_json fence/prose tolerance
- invoke_llm_structured ladder: native method fallback and prompt_json rung
  with self-correcting retry
"""

import asyncio
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from backend.agent.llm import (
    _extract_json,
    _invoke_prompt_json,
    _merge_consecutive_humans,
    _prepare_messages,
    build_system_prompt,
    invoke_llm_structured,
)
from backend.core.llm import (
    message_text,
    structured_method_ladder,
    supports_temperature,
)


class Decision(BaseModel):
    rationale: str
    score: int


# ---------------------------------------------------------------------------
# supports_temperature
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", [
    "gpt-4.1", "gpt-4o-mini", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    "claude-opus-4-6", "llama-3.3-70b-versatile", "mistral-large-latest",
    "command-r-plus-08-2024", "grok-3",
])
def test_supports_temperature_true(model):
    assert supports_temperature(model) is True


@pytest.mark.parametrize("model", [
    "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-5", "claude-fable-5",
    "claude-mythos-5", "gpt-5.4-mini", "gpt-5", "o1", "o3-mini",
    "anthropic.claude-opus-4-8",  # Bedrock-prefixed IDs
])
def test_supports_temperature_false(model):
    assert supports_temperature(model) is False


# ---------------------------------------------------------------------------
# message_text
# ---------------------------------------------------------------------------

def test_message_text_plain_string():
    assert message_text(AIMessage(content="hello")) == "hello"


def test_message_text_block_list():
    msg = AIMessage(content=[
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": "part one, "},
        {"type": "text", "text": "part two"},
        "raw tail",
    ])
    assert message_text(msg) == "part one, part tworaw tail"


def test_message_text_accepts_raw_content():
    assert message_text("already text") == "already text"


# ---------------------------------------------------------------------------
# build_system_prompt format per provider
# ---------------------------------------------------------------------------

_STATE = {"context": "universal", "current_year": 2026, "available_tools": {}}


def test_system_prompt_blocks_for_anthropic():
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "anthropic"}):
        content = build_system_prompt(_STATE, "node instructions", node="response")
    assert isinstance(content, list)
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert "node instructions" in content[0]["text"]
    assert "current_year" in content[1]["text"]


def test_system_prompt_string_for_other_providers():
    with patch("backend.agent.llm.NODE_PROVIDERS", {"react": "groq"}):
        content = build_system_prompt(_STATE, "node instructions", node="react")
    assert isinstance(content, str)
    assert "node instructions" in content
    assert "current_year" in content


def test_system_prompt_merges_extra_context():
    with patch("backend.agent.llm.NODE_PROVIDERS", {"scrape": "openai"}):
        content = build_system_prompt(
            _STATE, "scrape instructions", node="scrape",
            extra_context={"topic": "AAPL guidance"},
        )
    assert '"topic": "AAPL guidance"' in content


# ---------------------------------------------------------------------------
# _prepare_messages
# ---------------------------------------------------------------------------

def test_prepare_messages_injects_human_when_empty():
    msgs = _prepare_messages([], "google_genai")
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)


def test_prepare_messages_merges_consecutive_humans_for_strict_providers():
    msgs = [HumanMessage(content="one"), HumanMessage(content="two"), AIMessage(content="ok")]
    out = _prepare_messages(msgs, "google_genai")
    assert len(out) == 2
    assert message_text(out[0]) == "one\n\ntwo"


def test_prepare_messages_leaves_non_strict_providers_alone():
    msgs = [HumanMessage(content="one"), HumanMessage(content="two")]
    assert _prepare_messages(msgs, "openai") == msgs


def test_merge_consecutive_humans_noop_when_alternating():
    msgs = [HumanMessage(content="q"), AIMessage(content="a"), HumanMessage(content="q2")]
    assert _merge_consecutive_humans(msgs) == msgs


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    assert _extract_json('Here is the result: {"a": 1} hope it helps') == {"a": 1}


def test_extract_json_no_object_raises():
    with pytest.raises(ValueError):
        _extract_json("no json here")


# ---------------------------------------------------------------------------
# Structured-output ladder
# ---------------------------------------------------------------------------

class _FakeStructuredModel:
    """with_structured_output result that succeeds or fails per configuration."""

    def __init__(self, outcome):
        self._outcome = outcome

    async def ainvoke(self, messages):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeBaseModel:
    """Base chat model whose structured methods behave per `method_outcomes`,
    and whose plain ainvoke returns queued raw completions (prompt_json rung)."""

    def __init__(self, method_outcomes=None, raw_responses=None):
        self.method_outcomes = method_outcomes or {}
        self.raw_responses = list(raw_responses or [])
        self.methods_tried = []
        self.raw_calls = []

    def with_structured_output(self, schema, method=None):
        self.methods_tried.append(method)
        if method not in self.method_outcomes:
            raise NotImplementedError(f"method {method} unsupported")
        return _FakeStructuredModel(self.method_outcomes[method])

    async def ainvoke(self, messages):
        self.raw_calls.append(messages)
        return AIMessage(content=self.raw_responses.pop(0))


_LADDER_STATE = {
    "context": "",
    "current_year": 2026,
    "available_tools": {},
    "dialogue": [HumanMessage(content="go")],
}


def _run_structured(fake, provider="openai"):
    with (
        patch("backend.agent.llm.get_node_model", return_value=fake),
        patch("backend.agent.llm.NODE_PROVIDERS", {"plan": provider}),
    ):
        return asyncio.run(
            invoke_llm_structured(_LADDER_STATE, "instructions", Decision, node="plan")
        )


def test_ladder_first_method_succeeds():
    expected = Decision(rationale="ok", score=1)
    fake = _FakeBaseModel(method_outcomes={"function_calling": expected})
    assert _run_structured(fake) is expected
    assert fake.methods_tried == ["function_calling"]


def test_ladder_falls_back_to_second_method():
    expected = Decision(rationale="ok", score=2)
    fake = _FakeBaseModel(method_outcomes={
        "function_calling": RuntimeError("tools not supported"),
        "json_mode": expected,
    })
    assert _run_structured(fake) is expected
    assert fake.methods_tried == ["function_calling", "json_mode"]


def test_ladder_none_result_triggers_fallback():
    expected = Decision(rationale="ok", score=3)
    fake = _FakeBaseModel(method_outcomes={
        "function_calling": None,  # some providers return None on parse failure
        "json_mode": expected,
    })
    assert _run_structured(fake) is expected


def test_ladder_falls_through_to_prompt_json():
    fake = _FakeBaseModel(
        method_outcomes={},  # every native method raises NotImplementedError
        raw_responses=['{"rationale": "from prompt", "score": 7}'],
    )
    result = _run_structured(fake)
    assert result == Decision(rationale="from prompt", score=7)
    # prompt_json appends the schema instruction to the system prompt
    system = fake.raw_calls[0][0]
    assert "JSON Schema" in message_text(system)


def test_ladder_fatal_status_reraises_immediately():
    class RateLimited(Exception):
        status_code = 429

    fake = _FakeBaseModel(method_outcomes={"function_calling": RateLimited("slow down")})
    with pytest.raises(RateLimited):
        _run_structured(fake)
    assert fake.methods_tried == ["function_calling"]


def test_prompt_json_retries_on_validation_error():
    fake = _FakeBaseModel(raw_responses=[
        'not json at all',
        '```json\n{"rationale": "fixed", "score": 9}\n```',
    ])
    result = asyncio.run(
        _invoke_prompt_json(fake, "system text", [HumanMessage(content="go")], Decision)
    )
    assert result == Decision(rationale="fixed", score=9)
    # Retry conversation feeds the failure back before asking again
    retry_messages = fake.raw_calls[1]
    assert any("not valid" in message_text(m) for m in retry_messages)


def test_prompt_json_fails_after_retry():
    fake = _FakeBaseModel(raw_responses=["nope", "still nope"])
    with pytest.raises(ValueError, match="after retry"):
        asyncio.run(
            _invoke_prompt_json(fake, "system text", [HumanMessage(content="go")], Decision)
        )


def test_huggingface_ladder_is_prompt_json_only():
    assert structured_method_ladder("huggingface") == ("prompt_json",)


def test_unknown_provider_gets_default_ladder():
    assert structured_method_ladder("some_new_provider") == ("function_calling", "prompt_json")
