from __future__ import annotations

import json
import re
from typing import Any


def timeframe_key(timeframe: Any) -> str:
    return json.dumps(timeframe, sort_keys=True)


def timeframe_information_score(timeframe: Any) -> tuple[int, int, int]:
    """Score coverage, explicitness, and breadth for timeframe comparison."""
    if isinstance(timeframe, list):
        item_scores = [timeframe_information_score(item) for item in timeframe]
        max_period_count = max((score[0] for score in item_scores), default=0)
        explicitness = max((score[1] for score in item_scores), default=0)
        return (max(max_period_count, len(timeframe)), explicitness, len(timeframe))

    if not isinstance(timeframe, str):
        return (0, 0, 0)

    normalized = timeframe.lower().strip()
    years = [
        int(value)
        for value in re.findall(r"\b(\d+)\s*(?:fiscal\s*)?years?\b", normalized)
    ]
    quarters = [
        int(value)
        for value in re.findall(r"\b(\d+)\s*(?:fiscal\s*)?quarters?\b", normalized)
    ]

    if years:
        return (max(years) * 4, 2, 1)
    if quarters:
        return (max(quarters), 2, 1)
    if "latest available period" in normalized:
        return (1, 0, 1)
    if re.search(r"\b(?:fy|fiscal year|year|q[1-4])\b|\b20\d{2}\b", normalized):
        return (1, 2, 1)
    return (1, 1, 1)


def most_informative_timeframe(timeframes: list[Any]) -> Any:
    """Pick the richest timeframe, using frequency only to break ties."""
    counts: dict[str, int] = {}
    values_by_key: dict[str, Any] = {}
    for timeframe in timeframes:
        key = timeframe_key(timeframe)
        counts[key] = counts.get(key, 0) + 1
        values_by_key[key] = timeframe

    selected_key = max(
        counts,
        key=lambda key: (timeframe_information_score(values_by_key[key]), counts[key]),
    )
    return values_by_key[selected_key]


def matching_historical_timeframe(projection_timeframe: Any) -> Any:
    if isinstance(projection_timeframe, list):
        return [matching_historical_timeframe(item) for item in projection_timeframe]

    if not isinstance(projection_timeframe, str):
        return projection_timeframe

    normalized = projection_timeframe.lower().strip()
    years = re.findall(r"\b(\d+)\s*(?:fiscal\s*)?years?\b", normalized)
    quarters = re.findall(r"\b(\d+)\s*(?:fiscal\s*)?quarters?\b", normalized)

    if years:
        year_count = max(int(value) for value in years)
        return f"latest {year_count} fiscal years"
    if quarters:
        quarter_count = max(int(value) for value in quarters)
        return f"latest {quarter_count} fiscal quarters"
    return projection_timeframe


def ensure_historical_covers_projection(
    historical_timeframe: Any, projection_timeframe: Any
) -> Any:
    historical_score = timeframe_information_score(historical_timeframe)
    projection_score = timeframe_information_score(projection_timeframe)

    if historical_score[0] >= projection_score[0]:
        return historical_timeframe
    return matching_historical_timeframe(projection_timeframe)


def role_timeframes(
    information_requirements: list[dict[str, Any]], role: str, field: str
) -> list[Any]:
    return [
        task[field]
        for task in information_requirements
        if task["timeframe_role"] == role and task[field] is not None
    ]


def resolve_role_timeframes(
    information_requirements: list[dict[str, Any]]
) -> dict[str, Any]:
    historical_baseline_timeframes = role_timeframes(
        information_requirements, "historical_baseline", "historical_timeframe"
    )
    historical_baseline_timeframe = (
        most_informative_timeframe(historical_baseline_timeframes)
        if historical_baseline_timeframes
        else ["latest 3 fiscal years"]
    )

    projection_historical_timeframes = role_timeframes(
        information_requirements, "projection", "historical_timeframe"
    )
    projection_historical_timeframe = (
        most_informative_timeframe(projection_historical_timeframes)
        if projection_historical_timeframes
        else historical_baseline_timeframe
    )

    projection_timeframes = role_timeframes(
        information_requirements, "projection", "projection_timeframe"
    )
    projection_timeframe = (
        most_informative_timeframe(projection_timeframes)
        if projection_timeframes
        else ["next 5 fiscal years"]
    )
    projection_historical_timeframe = ensure_historical_covers_projection(
        projection_historical_timeframe,
        projection_timeframe,
    )

    return {
        "current_historical_timeframe": "latest available period",
        "historical_baseline_timeframe": historical_baseline_timeframe,
        "projection_historical_timeframe": projection_historical_timeframe,
        "projection_timeframe": projection_timeframe,
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def sync_entity_time_periods(task: dict[str, Any]) -> None:
    task["entities"]["time_periods"] = [
        *as_list(task["historical_timeframe"]),
        *as_list(task["projection_timeframe"]),
    ]


def apply_normalized_timeframes(
    task: dict[str, Any], normalized_timeframes: dict[str, Any]
) -> None:
    role = task["timeframe_role"]

    if role == "current":
        task["historical_timeframe"] = normalized_timeframes[
            "current_historical_timeframe"
        ]
        task["projection_timeframe"] = None
    elif role == "historical_baseline":
        task["historical_timeframe"] = normalized_timeframes[
            "historical_baseline_timeframe"
        ]
        task["projection_timeframe"] = None
    elif role == "projection":
        task["historical_timeframe"] = normalized_timeframes[
            "projection_historical_timeframe"
        ]
        task["projection_timeframe"] = normalized_timeframes["projection_timeframe"]
    elif role == "structural":
        task["historical_timeframe"] = None
        task["projection_timeframe"] = None

    sync_entity_time_periods(task)


def normalize_information_requirement_timeframes(
    information_requirements: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    normalized_timeframes = resolve_role_timeframes(information_requirements)
    for task in information_requirements:
        apply_normalized_timeframes(task, normalized_timeframes)
    return information_requirements
