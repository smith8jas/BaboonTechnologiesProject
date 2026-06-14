"""Judge node: evaluates the response and decides whether to release, revise, or gather more data."""

import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from ..constants import JUDGE_LIMIT, REACT_LIMIT
from ..llm import invoke_llm_structured
from ..messages import messages_for_llm
from ..prompts import judge_prompt
from ..state import AgentState


logger = logging.getLogger(__name__)


class JudgeDecision(BaseModel):
    rationale: str
    verdict: Literal["end", "revise"]


async def judge_node(state: AgentState):
    """Evaluate response and decide whether to release to user, revise, or gather more data."""
    logger.info("Judge Node Activated")
    
    #Retrieves judge node counter from state class
    judge_count = state.get("judge_iterations", 0)

    #Stopper to avoid infinite loops
    if judge_count >= JUDGE_LIMIT - 2:
        result = {
            "judge_verdict": "end",
            "forced_response_due_to_recursion": True,
            "judge_iterations": judge_count + 1,
        }
        current_response = state.get("current_response", "")
        if current_response:
            result["messages"] = [AIMessage(content=current_response)]
        return result
    
    #Build judge's focused message list: all human messages + current_response in system prompt
    local_prompt = judge_prompt
    current_response = state.get("current_response", "")
    if current_response:
        local_prompt += f"\n\nResponse being evaluated:\n{current_response}"
    human_messages = [m for m in messages_for_llm(state) if isinstance(m, HumanMessage)]

    #Invokes llm call with prompt to fill in JudgeDecision
    try:
        decision: JudgeDecision = await invoke_llm_structured(
            state, local_prompt, JudgeDecision, node="judge", messages=human_messages
        )
    except Exception as exc:
        logger.warning("Judge structured output failed: %s", exc)
        return {
            "judge_verdict": "end",
            "judge_iterations": judge_count + 1,
        }

    result = {
        "judge_verdict": decision.verdict,
        "judge_iterations": judge_count + 1,
        "judge_rationale": decision.rationale,
    }

    # On approval, re-append current_response so it is always messages[-1] at END.
    if decision.verdict == "end" and current_response:
        result["messages"] = [AIMessage(content=current_response)]

    # Revise always routes to react — extend its limit if it's near the cap.
    if decision.verdict == "revise":
        react_count = state.get("react_iterations", 0)
        react_ext = state.get("judge_react_extensions", 0)
        if react_count >= REACT_LIMIT + react_ext - 2:
            result["judge_react_extensions"] = react_ext + 1

    return result
