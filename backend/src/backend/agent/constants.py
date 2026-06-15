"""Graph-wide constants shared by nodes, edges, runtime, and streaming."""

# Total budget shared by react and judge iterations.
# react = RECURSION_LIMIT / 1.42  (≈70% of budget)
# judge = RECURSION_LIMIT - REACT_LIMIT  (≈30% of budget)
RECURSION_LIMIT = 12
DEFAULT_RECURSION_LIMIT = RECURSION_LIMIT
REACT_LIMIT = round(RECURSION_LIMIT / 1.42)
JUDGE_LIMIT = RECURSION_LIMIT - REACT_LIMIT

SCRAPE_LIMIT = 10
SCRAPE_TOOL_NAME = "scrape_web"
SCRAPE_MIN_CONFIDENCE = 0.3
