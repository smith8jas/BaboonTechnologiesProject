"""Process-wide deep-plan flag set by the router and read by downstream nodes."""

_deep_plan = False


def set_deep_plan(value: bool) -> None:
    global _deep_plan
    _deep_plan = bool(value)


def is_deep_plan() -> bool:
    return _deep_plan
