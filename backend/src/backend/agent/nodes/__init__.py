"""Graph nodes — one module per node.

    router.py    routes between direct answer and the planning path
    plan.py      generates the initial tool-call batch
    tools.py     phase runner + exec_research/exec_calc execution nodes
    scrape.py    expands scrape topics into queries and gathers web results
    insight.py   interprets each batch tool result with parallel LLM calls
    react.py     evaluates tool results and loops or finishes
    response.py  composes the final user-facing answer
    judge.py     evaluates the response and decides whether to revise or release
"""

from .insight import insight_node
from .judge import judge_node
from .plan import plan_node
from .react import react_node
from .response import response_node
from .router import RouterDecision, router
from .scrape import ScrapeDecision, scrape_node
from .tools import exec_calc_node, exec_research_node, tools_node

__all__ = [
    "RouterDecision",
    "ScrapeDecision",
    "exec_calc_node",
    "exec_research_node",
    "insight_node",
    "judge_node",
    "plan_node",
    "react_node",
    "response_node",
    "router",
    "scrape_node",
    "tools_node",
]
