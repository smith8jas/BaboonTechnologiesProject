from __future__ import annotations

import ast
import json
import re
from typing import Any


def generate_tasks(query: str, app_context: Any) -> list[dict[str, Any]]:

    # Prompt 1 converts the raw user request into one or more clear questions.
    prompt_1 = """You are an intent normalizer for a financial valuation system.

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
    ]
    ]"""

    # Prompt 2 extracts only entities explicitly mentioned in those questions.
    prompt_2 = """
    You are an explicit entity extractor for a financial valuation system.

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
    - Include only real financial metrics in the financial metrics list. If it is not an explicit financial metric include it in topics (e.g., "profitable" goes in topics NOT in financial_metrics)
    - Do not answer anything.
    - Do not explain anything.

    Output format (strict JSON):
    {
    "companies": [],
    "securities_or_tickers": [],
    "assets": [],
    "financial_metrics": [],
    "valuation_methods": [],
    "industries": [],
    "regions_or_markets": [],
    "time_periods": [],
    "topics": []
    }
    """

    # Prompt 3 turns the questions and entities into executable information tasks.
    prompt_3 = """
    You are an information dependency planner for a financial valuation system.

    Task:
    Given:
    - questions_list: normalized core user questions
    - entities: explicitly identified entities

    Identify what the computer needs to know, retrieve, calculate, identify, or estimate to answer the user's questions.

    Represent the output as a JSON array of structured task objects.

    Each task object must contain the following fields:
    - task_ID
    - task
    - task_type
    - entities
    - timeframe_role
    - historical_timeframe
    - projection_timeframe
    - depends_on
    - required_output
    - priority
    - reason

    Definitions:
    - task_ID: unique string identifier for the task
    - task: a specific information requirement, retrieval requirement, calculation requirement, or identification requirement needed by the system.
    - task_type: one of "research", "calculate", or "analyze".
    - entities: the entities directly involved in the task. Exclude timefrimes from this field since they will be included in another field
    - timeframe_role: one of "current", "historical_baseline", "projection", or "structural". Choose the role based on the task's purpose, not merely on wording. The timeframe_role determines how timeframes are normalized later.
    - historical_timeframe: the historical period needed for the task. Use "latest available period" when the user does not specify a timeframe and the task is a factual/historical retrieval or calculation. Use a list for multi-period historical analysis. Use null if no historical period applies.
    - projection_timeframe: the future period needed for projection, forecast, or forward-looking tasks. Use a list for multi-period projections. Use null if no projection period applies.
    - depends_on: A list of prerequisite task_ID strings that must be completed before this task can be executed. Use an empty list if the task can be done right away.
    - required_output: A concise description of the exact information, result, or artifact that must be produced or retrieved, including its expected structure, representation, and data format.
    - priority: The relative importance of the task for successfully answering or completing the user’s query, classified as high, medium, or low.
    - reason: why this task is needed. If the task supports another generated task, explicitly reference that dependency.

    Timeframe role definitions:
    - current: tasks requiring the latest available point-in-time data, such as current market price, market capitalization, current valuation multiples, latest shares outstanding, latest debt, or latest cash.
    - historical_baseline: tasks requiring historical multi-period data to measure trends or support projections, such as latest 3 fiscal years revenue, net income, free cash flow, EPS, or EBITDA.
    - projection: tasks requiring future estimates, forecasts, forward valuation outputs, or projected financial metrics. Projection tasks may also include historical_timeframe when historical data is needed as the forecast baseline.
    - structural: tasks that identify methods, entities, benchmarks, peers, assumptions, or dependencies and do not require a financial period by themselves.

    Task type definitions:
    - research: go find unknown information. Use for tasks that retrieve, identify, collect, or look up information without performing calculations or judgment-heavy synthesis.
    - calculate: get a new value based on input values. Use for tasks that apply formulas, projections, valuation math, ratios, or numeric transformations to known or retrieved inputs.
    - analyze: get insights based on inputs. Use for tasks that compare, evaluate, interpret, rank, synthesize, or judge outputs from other tasks to support the user's answer.

    Entity rules:
    - Use entities from the provided entities input whenever possible.
    - Preserve the exact entity schema structure from the input entities object for every task, excluding timeframes.
    - Every task must contain all entity categories, even if some categories are empty lists.
    - Additional entities may only be introduced if they are required to complete the dependency chain needed to answer the question.
    - Unknown entities must never be fabricated as facts.
    - If a required entity is not explicitly available in the inputs or already established by another task, create a task to identify or retrieve that entity instead of naming it directly.
    - Do NOT hallucinate competitors, industries, benchmarks, macro factors, or relationships.
    - Example:
        Correct:
            "Identify Apple's most relevant competitors"
        Incorrect:
            "Apple competitors are Microsoft and Samsung"

    Task rules:
    - Order tasks from high-level tasks to lower-level prerequisite tasks.
    - Classify every task with task_type as "research", "calculate", or "analyze" based on the task's purpose.
    - If the user does not specify a timeframe, default factual or historical tasks to historical_timeframe: "latest available period".
    - If the user asks for a projection or forecast, use projection_timeframe for future-facing tasks and historical_timeframe for historical baseline tasks.
    - If the user asks an investment-decision question (e.g., "Should I invest", "Is this stock a buy", "Is this company undervalued"), include forward-looking valuation tasks by default.
    - For investment-decision questions with no projection horizon specified, use projection_timeframe: ["next 5 fiscal years"] for valuation or forecast tasks.
    - For investment-decision questions, include historical baseline tasks needed to support forecasts, usually historical_timeframe: ["latest 3 fiscal years"].
    - Normalize timeframes across tasks that belong to the same timeframe type and dependency group.
    - Do not force historical baseline tasks and projection tasks to use the same timeframe.
    - Break requirements into the smallest meaningful information units.
    - Include calculations only if they are necessary to answer the question.
    - Include prerequisite information needed to perform those calculations.
    - Include identification or retrieval tasks whenever unknown entities are required.
    - Do not name unknown peers, competitors, benchmarks, discount rates, assumptions, or market factors as facts. Create identification or estimation tasks for those unknowns.
    - Include the relevant entity in each task whenever applicable.
    - Include a timeframe for every task whenever applicable.
    - Do NOT answer the user's question.
    - Do NOT perform calculations.
    - Do NOT make assumptions.
    - Do NOT include vague tasks such as:
        - "get financial data"
        - "analyze company performance"
        - "retrieve market information"
    - Prefer explicit measurable tasks such as:
        - "Find Apple FY2024 revenue"
        - "Calculate Tesla net profit margin"
        - "Find Ford EV/EBITDA ratio"

    Reason rules:
    - Reasons should describe why the task is required.
    - If a task supports another generated task, explicitly reference that dependency.
    - Reasons should be concise and specific.

    task_ID rules:
    - task_IDs should should be written in the format TX where X is a number (e.g. "T1", "T2", "T3")
    - Each task should have a unique task_ID

    Output rules:
    - Return strict JSON only.
    - Return a JSON array.
    - Do not include explanations, comments, markdown, or additional text.

    Output format example:
    [
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
            "projection_timeframe": null,
            "depends_on": ["T2", "T4"],
            "required_output": "Quarterly revenue growth percentages for Tesla from Q1 2023 to Q4 2024 in structured JSON format",
            "priority": "high",
            "reason": "Needed to analyze profitability of Company X"
        }
    ]"""


    def strip_json_fence(output: str) -> str:
        # Some model responses wrap JSON in markdown fences; remove them before parsing.
        output = output.strip()
        fenced_json = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", output, re.DOTALL)
        return fenced_json.group(1).strip() if fenced_json else output

    def call_task_llm(task_prompt: str, *inputs: str | list[str]) -> Any:
        # Shared caller for prompts 1 and 2, with structured-output support when available.
        if not inputs:
            raise ValueError("At least one string or list input is required.")

        formatted_inputs: dict[str, str] = {}
        for index, input_value in enumerate(inputs, start=1):
            if isinstance(input_value, str):
                formatted_input = input_value
            elif isinstance(input_value, list):
                formatted_input = json.dumps(input_value)
            else:
                raise TypeError("Inputs must be strings or lists of strings.")

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

    def identify_information_requirements(
        questions_list: list[str],
        entities: dict[str, list[str]],
        prompt_3: str,
    ) -> list[dict[str, Any]]:
        # Run Prompt 3 and validate each generated task against the required schema.
        llm_output = app_context.ask_llm(
            prompt_3,
            questions_list=json.dumps(questions_list),
            entities=json.dumps(entities),
        )
        parsed_output = json.loads(strip_json_fence(llm_output)) if isinstance(llm_output, str) else llm_output

        if not isinstance(parsed_output, list):
            raise ValueError("Prompt 3 output must be a JSON array.")
        

        required_keys = {"task_ID", "task", "task_type", "entities", "timeframe_role", "historical_timeframe", "projection_timeframe", "depends_on", "required_output", "priority", "reason"}
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
            if not isinstance(task["task"], str):
                raise ValueError("Each Prompt 3 task field must be a string.")
            if not isinstance(task["task_ID"], str):
                raise ValueError("Each Prompt 3 task_ID field must be a string.")
            if task["task_type"] not in allowed_task_types:
                raise ValueError("Each Prompt 3 task_type must be research, calculate, or analyze.")
            if not isinstance(task["entities"], dict):
                raise ValueError("Each Prompt 3 entities field must be an object.")
            if not isinstance(task["depends_on"], list) or not all(isinstance(item, str) for item in task["depends_on"]):
                raise ValueError("Each Prompt 3 depends_on field must be a list of task_ID strings.")
            if not isinstance(task["required_output"], str):
                raise ValueError("Each Prompt 3 required_output field must be a string.")
            if task["priority"] not in {"high", "medium", "low"}:
                raise ValueError("Each Prompt 3 priority field must be high, medium, or low.")
            if task["timeframe_role"] not in allowed_timeframe_roles:
                raise ValueError("Each Prompt 3 timeframe_role must be current, historical_baseline, projection, or structural.")
            if task["historical_timeframe"] is not None and not isinstance(task["historical_timeframe"], (str, list)):
                raise ValueError("Each Prompt 3 historical_timeframe must be a string, list, or null.")
            if task["projection_timeframe"] is not None and not isinstance(task["projection_timeframe"], (str, list)):
                raise ValueError("Each Prompt 3 projection_timeframe must be a string, list, or null.")
            if not isinstance(task["reason"], str):
                raise ValueError("Each Prompt 3 reason field must be a string.")

        return parsed_output

    def normalize_information_requirement_timeframes(
        information_requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Normalize each role's timeframe while preferring broader, more informative periods.
        def timeframe_key(timeframe: Any) -> str:
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

        def most_informative_timeframe(timeframes: list[Any]) -> Any:
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

        def role_timeframes(role: str, field: str) -> list[Any]:
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

        def sync_entity_time_periods(task: dict[str, Any]) -> None:
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

    def print_information_requirements(
        information_requirements: list[dict[str, Any]],
        title: str,
    ) -> None:
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

    # Pipeline: normalize the request, extract entities, generate tasks, normalize timeframes.
    questions_list = call_task_llm(prompt_1, query)
    print("  ")
    print(questions_list)

    entities = call_task_llm(prompt_2, questions_list)
    print("  ")
    print(entities)

    information_requirements = identify_information_requirements(questions_list, entities, prompt_3)
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
