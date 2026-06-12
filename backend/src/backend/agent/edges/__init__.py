"""Conditional edges — one module per routing decision.

    after_router.py  router → plan_node | END
    after_plan.py    plan_node → tools | scrape_node | both | response_node
    after_react.py   react_node → tools | scrape_node | both | response_node
"""

from .after_plan import route_after_plan
from .after_react import route_after_react
from .after_router import route_after_router

__all__ = [
    "route_after_plan",
    "route_after_react",
    "route_after_router",
]
