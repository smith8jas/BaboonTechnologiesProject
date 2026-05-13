from __future__ import annotations

import ast
import json
import re
from typing import Any

def generate_tasks(query, app_context, System_context):

    # Shared output rules injected into prompts that return structured data
    SHARED_OUTPUT_RULES = """\
    - Do not answer the user's question.
    - Do not perform calculations.
    - Do not make assumptions.
    - Do not explain anything."""

    ENTITY_SCHEMA = {
    "companies": [],
    "securities_or_tickers": [],
    "assets": [],
    "financial_metrics": [],
    "valuation_methods": [],
    "industries": [],
    "regions_or_markets": [],
    "time_periods": [],
    "topics": []}

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
    "reason"]

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
            "topics": ["profitability"]
        },
        "timeframe_role": "historical_baseline",
        "historical_timeframe": ["2025", "2026"],
        "projection_timeframe": None,
        "depends_on": ["T2", "T4"],
        "required_output": "Quarterly revenue growth percentages for Tesla from Q1 2023 to Q4 2024 in structured JSON format",
        "priority": "high",
        "reason": "Needed to analyze profitability of Company X"}]
    
    _entity_schema_str = json.dumps(ENTITY_SCHEMA, indent=2)
    _task_fields_str   = "\n".join(f"    - {f}" for f in TASK_FIELDS)
    _task_example_str  = json.dumps(TASK_EXAMPLE, indent=4)

    prompt_1 = f"""You are an intent normalizer {System_context}.

    Task:
    Convert the user query into a structured list of normalized user questions.
    Each output question should answer: "What does the user want to know?"

    Rules:
    - Return a Python list of strings
    - Return exactly one normalized question for each distinct question asked by the user
    - Do not split one user question merely because it mentions multiple companies, metrics, methods, or analytical dimensions
    - Do not decompose the user question into data requirements, calculations, retrieval tasks, assumptions, or analysis steps
    - Do not introduce methods, metrics, competitors, benchmarks, assumptions, or subtopics unless explicitly mentioned by the user
    - Preserve the user's decision or information goal
    - Each question must be explicit and self-contained
    - Do not use pronouns (e.g., "it", "they")
    - Do not introduce entities not mentioned in the query
    - Do not answer or explain anything
    - Keep questions concise and professional
    - Avoid redundancy

    Output format (strict):

    [
    "Question 1",
    "Question 2",
    ...
    ]"""

    prompt_2 = f"""You are an explicit entity extractor {System_context}.

    Task:
    From the provided list of normalized user questions, extract and classify only entities that are explicitly mentioned.

    Definition:
    An entity is "explicitly mentioned" only if it appears directly in the text. Do not infer, expand, or derive entities from context.

    Rules:
    - Extract only entities from the normalized user questions.
    - Do NOT infer industries, competitors, macro factors, or relationships.
    - Do NOT infer tickers unless a ticker or security identifier is explicitly mentioned.
    - Do NOT infer valuation methods, metrics, assumptions, timeframes, or required calculations.
    - Do NOT expand entities (e.g., "Apple" -> "technology industry" is NOT allowed).
    - Extract entities exactly as they appear, with minimal normalization only when it preserves the same explicit entity (e.g., "Apple" -> "Apple Inc." is allowed if clearly the same company).
    - Broad user goals such as "Should I invest in Apple?" may be classified as topics (e.g., "investment decision"), but should not create inferred metrics or valuation methods.
    - If uncertain whether something is explicitly mentioned, exclude it.
    - If a category has no entities, return an empty list.
    - Include only real financial metrics in the financial metrics list. If it is not an explicit financial metric include it in topics (e.g., "profitable" goes in topics NOT in financial_metrics).
    {SHARED_OUTPUT_RULES}

    Output format (strict JSON):
    {_entity_schema_str}"""

    prompt_3 = f"""You are an information dependency planner {System_context}.

    Task:
    Given:
    - questions_list: normalized core user questions
    - entities: explicitly identified entities

    Identify what the computer needs to know, retrieve, calculate, identify, or estimate to answer the user's questions.

    Represent the output as a JSON array of structured task objects.

    Each task object must contain the following fields:
    {_task_fields_str}

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
    {_entity_schema_str}
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
    - Return strict JSON only — no explanations, comments, or markdown.
    - Return a JSON array.

    Output format example:
    {_task_example_str}"""

    # Pipeline: normalize the request, extract entities, generate tasks, normalize timeframes.
    questions_list = call_task_llm(prompt_1, app_context, query)
    print("  ")
    print(questions_list)

    entities = call_task_llm(prompt_2, app_context, questions_list)
    print("  ")
    print(entities)

    information_requirements = identify_information_requirements(app_context, questions_list, entities, prompt_3, TASK_FIELDS)
    print_information_requirements(
        information_requirements,
        "Output 3 - Information Requirements Before Timeframe Normalization",
    )
    information_requirements = normalize_information_requirement_timeframes(information_requirements)
    print_information_requirements(
        information_requirements,
        "Output 3 - Information Requirements After Timeframe Normalization",
    )
  
    return information_requirements


def strip_json_fence(output):
        # Some model responses wrap JSON in markdown fences; remove them before parsing.
        output = output.strip()
        fenced_json = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", output, re.DOTALL)
        return fenced_json.group(1).strip() if fenced_json else output

def call_task_llm(task_prompt, app_context, *inputs):
        # Shared caller for prompts 1 and 2, with structured-output support when available.

        formatted_inputs: dict[str, str] = {}
        for index, input_value in enumerate(inputs, start=1):
            if isinstance(input_value, str):
                formatted_input = input_value
            elif isinstance(input_value, list):
                formatted_input = json.dumps(input_value)

            formatted_inputs[f"input_{index}"] = formatted_input

        prompt_parts = [task_prompt]
        for key, value in formatted_inputs.items():
            prompt_parts.append(f"{key}: {value}")

        is_question_task = "Return a Python list of strings" in task_prompt
        is_entity_task = "Output format (strict JSON)" in task_prompt

        if is_question_task:
            output_schema = {
                "title": "TaskQuestions",
                "description": "Normalized core questions extracted from the user query.",
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["questions"],
                "additionalProperties": False,
            }
            prompt_parts.append(
                'Return valid JSON only, exactly matching this shape: {"questions": ["Question 1"]}'
            )
        elif is_entity_task:
            required_keys = {
                "companies",
                "securities_or_tickers",
                "assets",
                "financial_metrics",
                "valuation_methods",
                "industries",
                "regions_or_markets",
                "time_periods",
                "topics",
            }
            output_schema = {
                "title": "ExtractedFinancialEntities",
                "description": "Entities explicitly mentioned in normalized financial valuation questions.",
                "type": "object",
                "properties": {
                    key: {"type": "array", "items": {"type": "string"}}
                    for key in required_keys
                },
                "required": sorted(required_keys),
                "additionalProperties": False,
            }
            prompt_parts.append("Return valid JSON only, with all required keys and no extra keys.")
        else:
            output_schema = None

        prompt = "\n\n".join(prompt_parts)

        def validate_question_output(output: Any) -> list[str]:
            # Accept either the target JSON shape or a raw list for backward compatibility.
            if isinstance(output, dict):
                parsed_output = output.get("questions")
            elif isinstance(output, list):
                parsed_output = output
            elif isinstance(output, str):
                clean_output = strip_json_fence(output)
                try:
                    json_output = json.loads(clean_output)
                    parsed_output = json_output.get("questions") if isinstance(json_output, dict) else json_output
                except json.JSONDecodeError:
                    parsed_output = ast.literal_eval(clean_output)
            else:
                raise ValueError("LLM output must be a list of strings.")

            if not isinstance(parsed_output, list) or not all(isinstance(item, str) for item in parsed_output):
                raise ValueError("LLM output must be a Python list of strings.")
            return parsed_output

        def validate_entity_output(output: Any) -> dict[str, list[str]]:
            # Enforce the fixed entity schema so downstream task generation is predictable.
            required_keys = {
                "companies",
                "securities_or_tickers",
                "assets",
                "financial_metrics",
                "valuation_methods",
                "industries",
                "regions_or_markets",
                "time_periods",
                "topics",
            }
            parsed_output = json.loads(strip_json_fence(output)) if isinstance(output, str) else output
            if set(parsed_output) != required_keys:
                raise ValueError("LLM JSON output does not match the required entity keys.")
            if not all(
                isinstance(value, list) and all(isinstance(item, str) for item in value)
                for value in parsed_output.values()
            ):
                raise ValueError("Each LLM JSON output field must be a list of strings.")
            return parsed_output

        if output_schema is not None:
            try:
                structured_llm = app_context.CHAT_MODEL.with_structured_output(output_schema)
                structured_output = structured_llm.invoke(prompt)
                if is_question_task:
                    return validate_question_output(structured_output)
                if is_entity_task:
                    return validate_entity_output(structured_output)
            except NotImplementedError:
                pass

        llm_output = app_context.ask_llm(prompt)

        if is_question_task:
            return validate_question_output(llm_output)

        if is_entity_task:
            return validate_entity_output(llm_output)

        return llm_output

def identify_information_requirements(app_context, questions_list, entities,prompt_3, required_keys):
        # Run Prompt 3 and validate each generated task against the required schema.
        llm_output = app_context.ask_llm(
            prompt_3,
            questions_list=json.dumps(questions_list),
            entities=json.dumps(entities),
        )
        parsed_output = json.loads(strip_json_fence(llm_output)) if isinstance(llm_output, str) else llm_output    

        required_keys = set(required_keys)
        allowed_task_types = {"research", "calculate", "analyze"}
        allowed_timeframe_roles = {"current", "historical_baseline", "projection", "structural"}
        for task in parsed_output:
            if isinstance(task, dict) and "timeframe" in task:
                task["historical_timeframe"] = task.pop("timeframe")
                task["projection_timeframe"] = None
            if not isinstance(task, dict) or set(task) != required_keys:
                actual_keys = set(task) if isinstance(task, dict) else set()
                missing_keys = sorted(required_keys - actual_keys)
                extra_keys = sorted(actual_keys - required_keys)
                raise ValueError(
                    "Each Prompt 3 task must contain exactly these fields: "
                    f"{sorted(required_keys)}. "
                    f"Missing fields: {missing_keys}. Extra fields: {extra_keys}."
                )

        return parsed_output

def normalize_information_requirement_timeframes(information_requirements):
        # Normalize each role's timeframe while preferring broader, more informative periods.
        def timeframe_key(timeframe):
            return json.dumps(timeframe, sort_keys=True)

        def timeframe_information_score(timeframe: Any) -> tuple[int, int, int]:
            # Higher scores represent timeframes with more coverage or clearer specificity.
            if isinstance(timeframe, list):
                item_scores = [timeframe_information_score(item) for item in timeframe]
                max_period_count = max((score[0] for score in item_scores), default=0)
                explicitness = max((score[1] for score in item_scores), default=0)
                return (max(max_period_count, len(timeframe)), explicitness, len(timeframe))

            if not isinstance(timeframe, str):
                return (0, 0, 0)

            normalized = timeframe.lower().strip()
            years = [int(value) for value in re.findall(r"\b(\d+)\s*(?:fiscal\s*)?years?\b", normalized)]
            quarters = [int(value) for value in re.findall(r"\b(\d+)\s*(?:fiscal\s*)?quarters?\b", normalized)]

            if years:
                return (max(years) * 4, 2, 1)
            if quarters:
                return (max(quarters), 2, 1)
            if "latest available period" in normalized:
                return (1, 0, 1)
            if re.search(r"\b(?:fy|fiscal year|year|q[1-4])\b|\b20\d{2}\b", normalized):
                return (1, 2, 1)
            return (1, 1, 1)

        def most_informative_timeframe(timeframes):
            # Pick the richest timeframe; use frequency only to break ties.
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

        def role_timeframes(role, field):
            # Collect existing timeframe values for one timeframe role and field.
            return [
                task[field]
                for task in information_requirements
                if task["timeframe_role"] == role and task[field] is not None
            ]

        current_historical_timeframe = "latest available period"
        historical_baseline_timeframes = role_timeframes("historical_baseline", "historical_timeframe")
        historical_baseline_timeframe = (
            most_informative_timeframe(historical_baseline_timeframes)
            if historical_baseline_timeframes
            else ["latest 3 fiscal years"]
        )
        projection_historical_timeframes = role_timeframes("projection", "historical_timeframe")
        projection_historical_timeframe = (
            most_informative_timeframe(projection_historical_timeframes)
            if projection_historical_timeframes
            else historical_baseline_timeframe
        )
        projection_timeframes = role_timeframes("projection", "projection_timeframe")
        projection_timeframe = (
            most_informative_timeframe(projection_timeframes)
            if projection_timeframes
            else ["next 5 fiscal years"]
        )

        def sync_entity_time_periods(task):
            # Keep the legacy entities.time_periods field aligned with normalized fields.
            task["entities"]["time_periods"] = []
            if task["historical_timeframe"] is not None:
                historical_periods = task["historical_timeframe"]
                if not isinstance(historical_periods, list):
                    historical_periods = [historical_periods]
                task["entities"]["time_periods"].extend(historical_periods)
            if task["projection_timeframe"] is not None:
                projection_periods = task["projection_timeframe"]
                if not isinstance(projection_periods, list):
                    projection_periods = [projection_periods]
                task["entities"]["time_periods"].extend(projection_periods)

        for task in information_requirements:
            role = task["timeframe_role"]

            if role == "current":
                task["historical_timeframe"] = current_historical_timeframe
                task["projection_timeframe"] = None
            elif role == "historical_baseline":
                task["historical_timeframe"] = historical_baseline_timeframe
                task["projection_timeframe"] = None
            elif role == "projection":
                task["historical_timeframe"] = projection_historical_timeframe
                task["projection_timeframe"] = projection_timeframe
            elif role == "structural":
                task["historical_timeframe"] = None
                task["projection_timeframe"] = None

            sync_entity_time_periods(task)

        return information_requirements

def print_information_requirements(information_requirements, title):
    # Print generated tasks before and after normalization for debugging.
    print(" ")
    print(title)
    print("-" * 80)
    for row_number, task in enumerate(information_requirements, start=1):
        print(f"Row {row_number}")
        if "task_ID" in task:
            print(f"Task ID: {task['task_ID']}")
        print(f"Task: {task['task']}")
        if "task_type" in task:
            print(f"Task Type: {task['task_type']}")
        print(f"Timeframe Role: {task['timeframe_role']}")
        print(f"Historical Timeframe: {json.dumps(task['historical_timeframe'])}")
        print(f"Projection Timeframe: {json.dumps(task['projection_timeframe'])}")
        if "depends_on" in task:
            print(f"Depends On: {json.dumps(task['depends_on'])}")
        if "required_output" in task:
            print(f"Required Output: {task['required_output']}")
        if "priority" in task:
            print(f"Priority: {task['priority']}")
        print(f"Entities: {json.dumps(task['entities'])}")
        print(f"Reason: {task['reason']}")
        print("-" * 80)