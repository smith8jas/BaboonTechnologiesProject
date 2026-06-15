"""Conditional edges — one module per routing decision.

    after_router.py  router → plan_node | END
    after_plan.py    plan_node → tools | scrape_node | both | response_node
    after_react.py   react_node → tools | scrape_node | both | response_node
    after_judge.py   judge_node → response_node | react_node | END
"""

from .after_judge import route_after_judge
from .after_plan import route_after_plan
from .after_react import route_after_react
from .after_router import route_after_router

__all__ = [
    "route_after_judge",
    "route_after_plan",
    "route_after_react",
    "route_after_router",
]
