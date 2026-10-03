"""Tools that let Reachy run spoken math practice; the problems and checking live in ``math_practice``."""

import logging
from typing import Any

from talk_with_reachy_math import math_games, math_practice
from talk_with_reachy_math.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class NextMathProblem(Tool):
    """Open the next math problem for the person speaking now."""

    name = "next_math_problem"
    description = (
        "Start a round of a math game for the child speaking now, or switch to another game. A round has five "
        "problems; within a round, check_math_answer already gives you the next problem. "
        "Read the returned 'say' text exactly. Never work out or reveal the answer yourself."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "game": {
                "type": "string",
                "enum": list(math_practice.GAMES),
                "description": "The game the child picked. Leave it out to keep the current game.",
            },
            "theme": {
                "type": "string",
                "enum": list(math_games.THEMES),
                "description": "What the child likes, for stories and guessing games. Pass it when you learn what "
                "they like; it is saved for next time.",
            },
            "topic": {
                "type": "string",
                "enum": math_practice.topics(),
                "description": "Only for quick math, when the child asks for a topic; otherwise leave it out.",
            },
        },
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Open a problem and return the text to read."""
        topic, game, theme = (kwargs.get(k) for k in ("topic", "game", "theme"))
        result = math_practice.coach().next_problem(
            topic if isinstance(topic, str) else None,
            game if isinstance(game, str) else None,
            theme if isinstance(theme, str) else None,
        )
        logger.info("Tool call: next_math_problem %s %s", result.get("problem_id"), result.get("game"))
        return result


class CheckMathAnswer(Tool):
    """Check the child's answer to the open problem or helper question."""

    name = "check_math_answer"
    description = (
        "Check the child's answer to the current math problem or helper question. Pass exactly what the child "
        "said, even if it is wrong, unclear, 'I don't know', or not a number. Then follow the returned instructions."
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
