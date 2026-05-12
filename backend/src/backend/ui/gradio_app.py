from __future__ import annotations

import gradio as gr

from backend.planning.task_generation import run_task_generation


def chat(message: str, history: object) -> str:
    try:
        run_task_generation(message)
    except Exception as exc:
        print(f"[task-generation skipped] {exc}", flush=True)

    return "Task generation ran for your message. Chat response generation is not connected yet."


def build_ui() -> gr.ChatInterface:
    return gr.ChatInterface(fn=chat)
