"""Render the LangGraph agent topology to a PNG.

Usage (from backend/):
    uv run python -m backend.agent.agent_plot

Output: src/images/agent_graph.png
"""

from __future__ import annotations

from pathlib import Path

from backend.agent.graph import initialize_agent

# agent/ -> backend/ -> src/ ; images dir lives at src/images
IMAGES_DIR = Path(__file__).resolve().parents[2] / "images"
OUTPUT_PATH = IMAGES_DIR / "agent_graph1.png"


def export_png() -> Path:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    agent = initialize_agent()          # compiled StateGraph
    drawable = agent.get_graph()        # networkx-style graph LangGraph builds

    # Preferred: Mermaid render (matches the auto-exported PDF style).
    # Requires network access to mermaid.ink.
    try:
        drawable.draw_mermaid_png(output_file_path=str(OUTPUT_PATH))
        print(f"[mermaid] wrote {OUTPUT_PATH}")
        return OUTPUT_PATH
    except Exception as exc:  # noqa: BLE001 - fall back to offline renderer
        print(f"[mermaid] failed ({exc}); trying graphviz")

    # Offline fallback: requires `uv add pygraphviz`.
    drawable.draw_png(str(OUTPUT_PATH))
    print(f"[graphviz] wrote {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    export_png()