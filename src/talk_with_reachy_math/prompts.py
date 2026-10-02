"""Resolve active profile prompts and voice settings."""

import logging
from pathlib import Path

from talk_with_reachy_math import voice_id, math_practice
from talk_with_reachy_math.config import config, get_default_voice
from talk_with_reachy_math.memory import format_memory_for_prompt
from talk_with_reachy_math.profile_store import (
    DEFAULT_PROFILE_NAME,
    ProfileDefinition,
    ProfileFormatError,
    read_profile,
    read_packaged_default_profile,
)
from talk_with_reachy_math.profile_toolsets import read_profile_tool_names


logger = logging.getLogger(__name__)

DEFAULT_GREETING_PROMPT = (
    "Start the conversation now with a brief, spontaneous greeting in character. "
    "Keep it to one sentence, invite the user in naturally, and vary the wording each time."
)

# Replaces the shared memory list when voice ID is on: memories are per person and
# arrive in a system note whenever the person speaking changes.
VOICE_ID_GUIDANCE = (
    "Several different people may talk with you. A voice recognition system tells you who is speaking: "
    'whenever the speaker changes, you receive a system note starting with "Voice ID:" that names the person '
    "(or gives a label such as V003 for a voice without a name) and lists what you remember about them. "
    "The note can be wrong; if something does not fit, ask gently. "
    "What you remember about one person belongs to that person only: never mention it to anyone else. "
    "The remember and forget tools act on the person speaking now. When someone tells you their name, save it."
)

# Added when the active profile has the math_practice tools.
MATH_GUIDANCE = (
    "You play short spoken math games with children aged about 10 to 13. "
    "When the conversation starts, say hi and invite them to play a quick math game with you. "
    'Invite them again when a system note starting with "Math practice:" says it is a good moment, '
    "or whenever they ask. If they say no, drop it and keep chatting. "
    "When they say yes, call next_math_problem right away and read its 'say' text exactly. "
    "Never work out a problem yourself, and never say or hint at an answer before the child has tried. "
    "Whenever the child answers a problem or a helper question, call check_math_answer with exactly what they said, "
    "even if it is wrong, unclear, or 'I don't know', and then do what its instructions say. "
    "The instructions break a hard problem into small helper questions: ask only those, one at a time, "
    "and do not make up other in-between questions. "
    "Talk like a friendly coach for a 10-year-old: short sentences, everyday words, and lots of encouragement. "
    "Never say 'wrong'; say 'Not quite yet' or 'Good try'. "
    "Keep to about five problems unless they want more, and call stop_math_practice when they want to stop."
)


def _math_tools_enabled(profile: str | None, instance_path: str | Path | None) -> bool:
    if not math_practice.enabled():
        return False
    try:
        return "math_practice" in read_profile_tool_names(profile, instance_path)
    except Exception as exc:  # a broken toolset file must not stop the session from starting
        logger.warning("Could not read the tools of profile %r: %s", profile, exc)
        return False


def _active_profile() -> ProfileDefinition:
    return read_profile(config.REACHY_MINI_CUSTOM_PROFILE)


def get_session_instructions(instance_path: str | Path | None = None) -> str:
    """Return instructions for the active profile with memory context."""
    selected_profile = config.REACHY_MINI_CUSTOM_PROFILE
    profile_name = selected_profile or DEFAULT_PROFILE_NAME
    try:
        profile = _active_profile()
        instructions = profile.instructions.strip()
    except (FileNotFoundError, ProfileFormatError) as exc:
        logger.warning("Failed to load profile %r: %s", profile_name, exc)
        instructions = ""

    if not instructions and selected_profile and selected_profile != DEFAULT_PROFILE_NAME:
        logger.warning("Using bundled default instructions because profile %r is incomplete", selected_profile)
        try:
            instructions = read_packaged_default_profile().instructions.strip()
        except (FileNotFoundError, ProfileFormatError) as exc:
            raise RuntimeError("Default profile has no usable instructions") from exc
    if not instructions:
        raise RuntimeError("Default profile has no usable instructions")

    if _math_tools_enabled(selected_profile, instance_path):
        instructions = f"{MATH_GUIDANCE}\n\n{instructions}"
    if voice_id.enabled():
        return f"{VOICE_ID_GUIDANCE}\n\n{instructions}"
    memory_prompt = format_memory_for_prompt(instance_path)
    if memory_prompt:
        return f"{memory_prompt}\n\n{instructions}"
    return instructions


def get_session_voice(default: str | None = None) -> str:
    """Return the active profile voice or the backend default."""
    fallback = get_default_voice() if default is None else default
    try:
        return _active_profile().voice or fallback
    except (FileNotFoundError, ProfileFormatError) as exc:
        logger.warning("Failed to load the active profile voice: %s", exc)
        return fallback


def get_session_greeting_prompt() -> str:
    """Return the active profile greeting prompt or the app default."""
    try:
        return _active_profile().greeting or DEFAULT_GREETING_PROMPT
    except (FileNotFoundError, ProfileFormatError) as exc:
        logger.warning("Failed to load the active profile greeting: %s", exc)
        return DEFAULT_GREETING_PROMPT
