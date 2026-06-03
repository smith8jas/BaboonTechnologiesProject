import os

from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.prebuilt import tools_condition

os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("OPENAI_API_KEY", "test")

from backend.Agent import graph


def test_plan_routes_to_native_tools_node_when_tool_calls_exist():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_financials",
                        "args": {"ticker": "AAPL"},
                        "id": "financial-call",
                    },
                    {
                        "name": "get_market_data",
                        "args": {"ticker": "AAPL"},
                        "id": "market-call",
                    },
                ],
            )
        ],
        "context": "",
        "current_year": 2026,
        "available_tools": [],
    }

    assert tools_condition(state) == "tools"


def test_plan_ends_when_no_tool_calls_exist():
    state = {
        "messages": [AIMessage(content="Please provide a ticker.")],
        "context": "",
        "current_year": 2026,
        "available_tools": [],
    }

    assert tools_condition(state) == END


def test_tools_node_edges_to_plan_node():
    agent = graph.initialize_agent()

    assert any(edge.source == "tools" and edge.target == "plan_node" for edge in agent.get_graph().edges)


def test_response_node_does_not_emit_tool_calls(monkeypatch):
    def fake_invoke_llm(state, prompt):
        return AIMessage(content="Final answer")

    monkeypatch.setattr(graph, "_invoke_llm", fake_invoke_llm)

    result = graph.response_node(
        {
            "messages": [
                ToolMessage(
                    content="financials done",
                    name="get_financials",
                    tool_call_id="financial-call",
                ),
            ],
            "context": "",
            "current_year": 2026,
            "available_tools": [],
        }
    )

    assert result["messages"][-1].content == "Final answer"
    assert not getattr(result["messages"][-1], "tool_calls", None)


def test_router_prompt_mentions_greetings():
    prompt = graph.router_prompt.lower()
    assert "valuation or closely related financial analysis" in prompt
    assert "capabilities and limitations" in prompt
    assert "plan_node" in prompt


def test_plan_prompt_refers_to_state_available_tools():
    prompt = graph.plan_prompt.lower()
    assert "state.available_tools" in prompt
    assert "capabilities in the catalog" in prompt
    assert "complete plan" in prompt
    assert "smallest plan" in prompt


def test_plan_prompt_does_not_name_concrete_tools():
    prompt = graph.plan_prompt.lower()
    assert "get_liquidity_ratios" not in prompt
    assert "get_solvency_ratios" not in prompt
    assert "get_profitability_ratios" not in prompt
    assert "run_dcf_valuation" not in prompt
    assert "ratio tool" not in prompt
    assert "valuation tool" not in prompt


def test_response_prompt_uses_response_node_name():
    assert "response node" in graph.response_prompt.lower()
