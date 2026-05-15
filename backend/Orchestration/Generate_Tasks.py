from __future__ import annotations

import json
import re
from typing import Any

try:
    from Normalize_Timeframes import normalize_information_requirement_timeframes
except ImportError:
    from .Normalize_Timeframes import normalize_information_requirement_timeframes


SYSTEM_CONTEXT = "for a financial valuation system"

ENTITY_SCHEMA = {
    "companies": [],
    "securities_or_tickers": [],
    "assets": [],
    "financial_metrics": [],
    "valuation_methods": [],
    "industries": [],
    "regions_or_markets": [],
    "time_periods": [],
    "topics": [],
}

TASK_FIELDS = [
    "task_ID",
    "task",
    "task_type",
    "entities",
    "timeframe_role",
    "historical_timeframe",
    "projection_timeframe",
    "depends_on",
    "required_output",
    "reason",
]

TASK_EXAMPLE = [
    {
        "task_ID": "T1",
        "task": "Calculate net profit margin of Company X",
        "task_type": "calculate",
        "entities": {
            "companies": ["Company X"],
            "securities_or_tickers": [],
            "assets": [],
            "financial_metrics": ["net profit margin"],
            "valuation_methods": [],
            "industries": [],
            "regions_or_markets": [],
            "time_periods": [],
            "topics": ["profitability"],
        },
        "timeframe_role": "historical_baseline",
        "historical_timeframe": ["2025", "2026"],
        "projection_timeframe": None,
        "depends_on": ["T2", "T4"],
        "required_output": "Net profit margin by period in structured JSON format",
        "reason": "Needed to analyze profitability of Company X",
    }
]

SHARED_OUTPUT_RULES = """\
- Do not answer the user's question.
- Do not perform calculations.
- Do not make assumptions.
- Do not explain anything."""


def generate_tasks(
    query: str,
    app_context,
    system_context: str = SYSTEM_CONTEXT,
    entity_schema: dict[str, list[str]] = ENTITY_SCHEMA,
    task_fields: list[str] = TASK_FIELDS,
    task_example: list[dict[str, Any]] = TASK_EXAMPLE,
) -> list[dict[str, Any]]:
    entity_schema_str = json.dumps(entity_schema, indent=2)
    task_fields_str = "\n".join(f"    - {field}" for field in task_fields)
    task_example_str = json.dumps(task_example, indent=4)

    intent_prompt = build_intent_and_entity_prompt(system_context, entity_schema_str)
    planning_prompt = build_information_planning_prompt(
        system_context,
        entity_schema_str,
        task_fields_str,
        task_example_str,
    )

    intent = call_task_llm(intent_prompt, app_context, query, entity_schema=entity_schema)
    questions_list = intent["questions"]
    entities = intent["entities"]

    print("  ")
    print(questions_list)
    print("  ")
    print(entities)

    information_requirements = identify_information_requirements(
        app_context,
        questions_list,
        entities,
        planning_prompt,
        task_fields,
    )
    print_information_requirements(
        information_requirements,
        "Output - Information Requirements Before Timeframe Normalization",
    )

    information_requirements = normalize_information_requirement_timeframes(
        information_requirements
    )
    print_information_requirements(
        information_requirements,
        "Output - Information Requirements After Timeframe Normalization",
    )

    return information_requirements


def build_intent_and_entity_prompt(system_context: str, entity_schema_str: str) -> str:
    return f"""You are an intent normalizer and explicit entity extractor {system_context}.

Task:
Rewrite the user query into direct, self-contained financial questions and extract only explicitly mentioned entities.

Question rules:
- Return exactly one normalized question for each distinct question asked by the user.
- Phrase each question as the actual question to be answered, not as a meta-question about what the user wants to know.
- Do not split one user question merely because it mentions multiple companies, metrics, methods, or analytical dimensions.
- Do not decompose the user question into data requirements, calculations, retrieval tasks, assumptions, or analysis steps.
- Preserve the user's decision or information goal.
- Each question must be explicit and self-contained.
- Do not use pronouns.
- Keep questions concise and professional.
- Avoid redundancy.

Entity rules:
- Extract only entities that appear directly in the user query or normalized questions.
- Do NOT infer industries, competitors, macro factors, relationships, tickers, valuation methods, metrics, assumptions, timeframes, or calculations.
- Do NOT expand entities unless the normalized name clearly refers to the same explicit entity.
- Broad user goals such as "Should I invest in Apple?" may be classified as topics, but should not create inferred metrics or valuation methods.
- If uncertain whether something is explicitly mentioned, exclude it.
- Include only real financial metrics in financial_metrics. Put non-metric concepts such as "profitable" in topics.
- If a category has no entities, return an empty list.
{SHARED_OUTPUT_RULES}

Output format (strict JSON):
{{
  "questions": ["Question 1"],
  "entities": {entity_schema_str}
}}"""


def build_information_planning_prompt(
    system_context: str,
    entity_schema_str: str,
    task_fields_str: str,
    task_example_str: str,
) -> str:
    return f"""You are an information dependency planner {system_context}.

Task:
Given:
- questions_list: normalized core user questions
- entities: explicitly identified entities

Identify what the computer needs to know, retrieve, calculate, identify, or estimate to answer the user's questions.

Represent the output as a JSON array of structured task objects.

Each task object must contain the following fields:
{task_fields_str}

Definitions:
- task_ID: unique string identifier for the task
- task: a specific information requirement, retrieval requirement, calculation requirement, or identification requirement needed by the system.
- task_type: one of "research", "calculate", or "analyze".
- entities: the entities directly involved in the task. Exclude time_periods from this field since they will be included in another field.
- timeframe_role: one of "current", "historical_baseline", "projection", or "structural". Choose the role based on the task's purpose, not merely on wording.
- historical_timeframe: the historical period needed for the task. Use "latest available period" when the user does not specify a timeframe. Use a list for multi-period historical analysis. Use null if no historical period applies.
- projection_timeframe: the future period needed for projection, forecast, or forward-looking tasks. Use a list for multi-period projections. Use null if no projection period applies.
- depends_on: a list of prerequisite task_ID strings that must be completed before this task can be executed. Use an empty list if the task has no dependencies.
- required_output: a concise description of the exact information, result, or artifact that must be produced or retrieved, including its expected structure and data format.
- reason: why this task is needed. If the task supports another generated task, explicitly reference that dependency.

Timeframe role definitions:
- current: tasks requiring the latest available point-in-time data (e.g. market price, market cap, shares outstanding, latest debt or cash).
- historical_baseline: tasks requiring historical multi-period data to measure trends or support projections (e.g. latest 3 fiscal years of revenue, net income, FCF, EPS, or EBITDA).
- projection: tasks requiring future estimates, forecasts, or forward valuation outputs. May also include historical_timeframe when historical data is needed as the forecast baseline.
- structural: tasks that identify methods, entities, benchmarks, peers, assumptions, or dependencies and do not require a financial period.

Task type definitions:
- research: retrieve, identify, collect, or look up information without performing calculations or judgment-heavy synthesis.
- calculate: apply formulas, projections, valuation math, ratios, or numeric transformations to known or retrieved inputs.
- analyze: compare, evaluate, interpret, rank, synthesize, or judge outputs from other tasks to support the user's answer.

Entity rules:
- Use entities from the provided entities input whenever possible.
- Remove time_periods. Preserve this exact entity schema structure for every task:
{entity_schema_str}
- Every task must contain all entity categories, even if some are empty lists.
- Additional entities may only be introduced if they are required to complete the dependency chain.
- Unknown entities must never be fabricated as facts. Create identification or retrieval tasks instead.
- Do NOT hallucinate competitors, industries, benchmarks, macro factors, or relationships.
- Example:
    Correct:   "Identify Apple's most relevant competitors"
    Incorrect: "Apple's competitors are Microsoft and Samsung"

Task rules:
- Order tasks from high-level to lower-level prerequisite tasks.
- If the user does not specify a timeframe, default factual or historical tasks to historical_timeframe: "latest available period".
- If the user asks for a projection or forecast, use projection_timeframe for future-facing tasks and historical_timeframe for baseline tasks.
- If the user asks an investment-decision question (e.g. "Should I invest", "Is this stock a buy", "Is this company undervalued"), include forward-looking valuation tasks by default.
- For investment-decision questions with no projection horizon specified, use projection_timeframe: ["next 5 fiscal years"].
- For investment-decision questions, include historical baseline tasks, usually historical_timeframe: ["latest 3 fiscal years"].
- Normalize timeframes across tasks that belong to the same timeframe type and dependency group.
- Break requirements into the smallest meaningful information units.
- Do NOT include vague tasks such as "get financial data" or "analyze company performance".
- Prefer explicit measurable tasks such as "Find Apple FY2024 revenue" or "Calculate Tesla net profit margin".
{SHARED_OUTPUT_RULES}

Reason rules:
- Describe why the task is required.
- If a task supports another task, explicitly reference that dependency by task_ID.
- Keep reasons concise and specific.

task_ID rules:
- Format: TX where X is a number (e.g. "T1", "T2", "T3").
- Each task_ID must be unique.

Output rules:
- Return strict JSON only - no explanations, comments, or markdown.
- Return a JSON array.

Output format example:
{task_example_str}"""


def strip_json_fence(output: str) -> str:
    output = output.strip()
    fenced_json = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", output, re.DOTALL)
    return fenced_json.group(1).strip() if fenced_json else output


def call_task_llm(
    task_prompt: str,
    app_context,
    *inputs: Any,
    entity_schema: dict[str, list[str]] = ENTITY_SCHEMA,
) -> Any:
    prompt_parts = [task_prompt]
    for index, input_value in enumerate(inputs, start=1):
        if isinstance(input_value, str):
            formatted_input = input_value
        elif isinstance(input_value, (list, dict)):
            formatted_input = json.dumps(input_value)
        else:
            formatted_input = str(input_value)
        prompt_parts.append(f"input_{index}: {formatted_input}")

    is_intent_task = "intent normalizer and explicit entity extractor" in task_prompt
    if is_intent_task:
        output_schema = build_intent_output_schema(entity_schema)
        prompt_parts.append(
            'Return valid JSON only, exactly matching this shape: {"questions": ["Question 1"], "entities": {...}}'
        )
    else:
        output_schema = None

    prompt = "\n\n".join(prompt_parts)

    if output_schema is not None:
        try:
            structured_llm = app_context.CHAT_MODEL.with_structured_output(output_schema)
            structured_output = structured_llm.invoke(prompt)
            return validate_intent_output(structured_output, entity_schema)
        except NotImplementedError:
            pass

    llm_output = app_context.ask_llm(prompt)
    if is_intent_task:
        return validate_intent_output(llm_output, entity_schema)
    return llm_output


def build_intent_output_schema(entity_schema: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "title": "NormalizedIntentAndEntities",
        "description": "Normalized questions and explicitly mentioned financial entities.",
        "type": "object",
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}},
            "entities": {
                "type": "object",
                "properties": {
                    key: {"type": "array", "items": {"type": "string"}}
                    for key in entity_schema
                },
                "required": sorted(entity_schema),
                "additionalProperties": False,
            },
        },
        "required": ["questions", "entities"],
        "additionalProperties": False,
    }


def validate_intent_output(
    output: Any, entity_schema: dict[str, list[str]]
) -> dict[str, Any]:
    parsed_output = json.loads(strip_json_fence(output)) if isinstance(output, str) else output
    if not isinstance(parsed_output, dict):
        raise ValueError("LLM output must be a JSON object.")

    questions = parsed_output.get("questions")
    entities = parsed_output.get("entities")
    if not isinstance(questions, list) or not all(
        isinstance(item, str) for item in questions
    ):
        raise ValueError("LLM output questions must be a list of strings.")
    if not isinstance(entities, dict) or set(entities) != set(entity_schema):
        raise ValueError("LLM output entities do not match the required entity keys.")
    if not all(
        isinstance(value, list) and all(isinstance(item, str) for item in value)
        for value in entities.values()
    ):
        raise ValueError("Each LLM entity field must be a list of strings.")

    return {"questions": questions, "entities": entities}


def identify_information_requirements(
    app_context,
    questions_list: list[str],
    entities: dict[str, list[str]],
    planning_prompt: str,
    required_keys: list[str],
) -> list[dict[str, Any]]:
    llm_output = app_context.ask_llm(
        planning_prompt,
        questions_list=json.dumps(questions_list),
        entities=json.dumps(entities),
    )
    parsed_output = (
        json.loads(strip_json_fence(llm_output)) if isinstance(llm_output, str) else llm_output
    )

    validate_information_requirements(parsed_output, required_keys)
    return parsed_output


def validate_information_requirements(
    tasks: Any, required_keys: list[str]
) -> None:
    if not isinstance(tasks, list):
        raise ValueError("Information requirements must be a JSON array.")

    required_key_set = set(required_keys)
    for task in tasks:
        if isinstance(task, dict) and "timeframe" in task:
            task["historical_timeframe"] = task.pop("timeframe")
            task["projection_timeframe"] = None

        if not isinstance(task, dict) or set(task) != required_key_set:
            actual_keys = set(task) if isinstance(task, dict) else set()
            missing_keys = sorted(required_key_set - actual_keys)
            extra_keys = sorted(actual_keys - required_key_set)
            raise ValueError(
                "Each generated task must contain exactly these fields: "
                f"{sorted(required_key_set)}. "
                f"Missing fields: {missing_keys}. Extra fields: {extra_keys}."
            )

        if not isinstance(task["depends_on"], list):
            raise ValueError("depends_on must be a list.")


def print_information_requirements(
    information_requirements: list[dict[str, Any]], title: str
) -> None:
    print(" ")
    print(title)
    print("-" * 80)
    for row_number, task in enumerate(information_requirements, start=1):
        print(f"Row {row_number}")
        print(f"Task ID: {task['task_ID']}")
        print(f"Task: {task['task']}")
        print(f"Task Type: {task['task_type']}")
        print(f"Timeframe Role: {task['timeframe_role']}")
        print(f"Historical Timeframe: {json.dumps(task['historical_timeframe'])}")
        print(f"Projection Timeframe: {json.dumps(task['projection_timeframe'])}")
        print(f"Depends On: {json.dumps(task['depends_on'])}")
        print(f"Required Output: {task['required_output']}")
        print(f"Entities: {json.dumps(task['entities'])}")
        print(f"Reason: {task['reason']}")
        print("-" * 80)
