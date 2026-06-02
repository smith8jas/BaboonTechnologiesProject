"""Agent-facing metadata helpers for LangChain tools."""


def agent_tool(
    tool,
    *,
    group: str,
    route: str,
    capability: str,
    requires_financials: bool = False,
):
    metadata = dict(getattr(tool, "metadata", None) or {})
    metadata["agent"] = {
        "group": group,
        "route": route,
        "capability": capability,
        "requires_financials": requires_financials,
    }
    tool.metadata = metadata
    return tool
