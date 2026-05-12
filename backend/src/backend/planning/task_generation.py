from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.core.config import settings


BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.planning.generate_tasks import generate_tasks


class PlanningChatModel:
    def with_structured_output(self, _schema: dict[str, Any]) -> None:
        raise NotImplementedError


CHAT_MODEL = PlanningChatModel()


def ask_llm(instruction: str, **inputs: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for task generation.")

    prompt_parts = [instruction]
    for key, value in inputs.items():
        prompt_parts.append(f"{key}: {value}")
    prompt = "\n\n".join(prompt_parts)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise financial valuation planning assistant. "
                    "Return only the requested structured output."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


def run_task_generation(query: str) -> None:
    generate_tasks(query, app_context=__import__(__name__, fromlist=[""]))
