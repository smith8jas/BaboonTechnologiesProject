"""Graph nodes — one module per node.

    router.py    routes between direct answer and the planning path
    plan.py      generates the initial tool-call batch
    tools.py     executes non-scrape tool calls against the data cache
    scrape.py    expands scrape topics into queries and gathers web results
    react.py     evaluates tool results and loops or finishes
    response.py  composes the final user-facing answer
    depth.py     shared deep-plan flag set by the router
"""

from .plan import plan_node
from .react import react_node
from .response import response_node
from .router import RouterDecision, router
from .scrape import ScrapeDecision, scrape_node
from .tools import tools_node

__all__ = [
    "RouterDecision",
    "ScrapeDecision",
    "plan_node",
    "react_node",
    "response_node",
    "router",
    "scrape_node",
    "tools_node",
]
