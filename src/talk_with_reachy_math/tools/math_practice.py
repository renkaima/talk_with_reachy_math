"""Tools that let Reachy run spoken math practice; the problems and checking live in ``math_practice``."""

import logging
from typing import Any

from talk_with_reachy_math import math_practice
from talk_with_reachy_math.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class NextMathProblem(Tool):
    """Open the next math problem for the person speaking now."""

    name = "next_math_problem"
    description = (
        "Get the next math practice problem for the child speaking now, chosen for their level. "
        "Read the returned 'say' text exactly. Never work out or reveal the answer yourself."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "enum": math_practice.topics(),
                "description": "Only if the child asks for a topic; otherwise leave it out.",
            },
        },
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Open a problem and return the text to read."""
        topic = kwargs.get("topic")
        result = math_practice.coach().next_problem(topic if isinstance(topic, str) else None)
        logger.info("Tool call: next_math_problem %s", result.get("problem_id"))
        return result


class CheckMathAnswer(Tool):
    """Check the child's answer to the open problem."""

    name = "check_math_answer"
    description = (
        "Check the child's answer to the current math problem. Pass exactly what the child said, "
        "even if it is wrong, unclear, or not a number. Then follow the returned instructions."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "child_answer": {
                "type": "string",
                "description": "The child's words, unchanged, for example 'um, seventy-two?' or 'three fourths'.",
            },
        },
        "required": ["child_answer"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Check the answer and return what to say next."""
        answer = kwargs.get("child_answer")
        if not isinstance(answer, str):
            return {"error": "child_answer must be the child's words as a string"}
        result = math_practice.coach().check_answer(answer)
        logger.info("Tool call: check_math_answer correct=%s", result.get("correct"))
        return result


class StopMathPractice(Tool):
    """End math practice."""

    name = "stop_math_practice"
    description = "End math practice when the child wants to stop or the conversation moves on."
    parameters_schema = {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Short reason, for example 'child wants to play'."},
        },
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Stop practice and return how it went."""
        reason = kwargs.get("reason")
        return math_practice.coach().stop(reason if isinstance(reason, str) else "")
