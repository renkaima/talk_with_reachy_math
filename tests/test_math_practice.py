"""Tests for spoken math practice: hearing answers, generating problems, levels, and logging."""

import re
import json
import random
import asyncio
from types import SimpleNamespace
from pathlib import Path
from fractions import Fraction as F

import pytest
from study_helpers import records, csv_rows

from talk_with_reachy_math import prompts, voice_id, study_log, math_practice
from talk_with_reachy_math.config import config
from talk_with_reachy_math.math_practice import (
    SKILLS,
    MathCoach,
    SkillProgress,
    numbers_in,
    parse_answer,
    record_result,
)
from talk_with_reachy_math.tools.math_practice import CheckMathAnswer, NextMathProblem


@pytest.mark.parametrize(
    ("said", "value"),
    [
        ("72", F(72)),
        ("um, seventy-two?", F(72)),
        ("It's 1,200", F(1200)),
        ("a hundred and five", F(105)),
        ("two thousand five hundred", F(2500)),
        ("twenty five twenty-fourths", F(25, 24)),
        ("1 and 1 twenty-fourth", F(25, 24)),
        ("three fourths", F(3, 4)),
        ("three quarters", F(3, 4)),
        ("3/4", F(3, 4)),
        ("3 over 4", F(3, 4)),
        ("3 out of 4", F(3, 4)),
        ("four sixths", F(2, 3)),
        ("a half", F(1, 2)),
        ("two and a half", F(5, 2)),
        ("2 and 3 fourths", F(11, 4)),
        ("zero point seven five", F(3, 4)),
        ("0.75", F(3, 4)),
        ("negative five", F(-5)),
        ("-5", F(-5)),
        ("negative three fourths", F(-3, 4)),
        ("x equals 9", F(9)),
        ("I think 12, no wait, 14", F(14)),
        ("$20", F(20)),
        ("25%", F(25)),
    ],
)
def test_spoken_answers_are_understood(said: str, value: F) -> None:
    """Digits, words, decimals, fractions, mixed numbers, and negatives; the last number counts."""
    assert parse_answer(said) == value


def test_no_number_means_no_answer() -> None:
    """Saying no number is not an answer."""
    assert parse_answer("I don't know") is None


def test_rounded_decimals_count_only_for_fractions_that_never_end() -> None:
    """0.33 is accepted for one third, but 0.8 is not accepted for 0.75."""
    assert math_practice.answer_matches(F(33, 100), F(1, 3))
    assert not math_practice.answer_matches(F(3, 10), F(1, 3))
    assert not math_practice.answer_matches(F(8, 10), F(3, 4))


def test_written_math_is_turned_into_words() -> None:
    """GSM8K writes 0.2 x 50 and 48/2; Reachy says 'times' and 'divided by'."""
    assert math_practice._say_expression("she earned 0.2 x 50 = $10") == "she earned 0.2 times 50 equals $10"
    assert math_practice._say_expression("48/2") == "48 divided by 2"
    assert math_practice._say_expression("a half-price km/h deal") == "a half-price km/h deal"


def test_numbers_are_said_the_way_children_say_them() -> None:
    """Fractions in words, decimals with a point, negatives with 'negative'."""
    assert math_practice.say_fraction(F(7, 6)) == "1 and 1 sixth"
    assert math_practice.say_fraction(F(-3, 4)) == "negative 3 fourths"
    assert math_practice.say_number(F(-5)) == "negative 5"
    assert math_practice.say_number(F(211, 100)) == "2.11"


def _operands(text: str, op: str) -> tuple[F, F]:
    """Return the numbers on each side of the operator word (in a problem, "minus" subtracts)."""
    left, right = text.split(op, 1)
    a, b = parse_answer(left), numbers_in(right)[0]
    assert a is not None
    return a, b


def _check_problem(problem: math_practice.Problem) -> None:
    """Recompute the answer from the spoken text, so the text and the answer can never disagree."""
    text, answer = problem.text, problem.answer
    ints = [F(int(n)) for n in re.findall(r"\d+", text)]
    if problem.skill == "multiply":
        assert answer == ints[0] * ints[1]
    elif problem.skill == "divide":
        assert answer == ints[0] / ints[1] and answer.denominator == 1
    elif problem.skill == "percent":
        assert answer == ints[0] * ints[1] / 100 and answer.denominator == 1
    elif problem.skill in ("integers", "decimals", "fractions"):
        op = next(w for w in (" plus ", " minus ", " times ", " of ") if w in text)
        x, y = _operands(text, op)
        expected = {" plus ": x + y, " minus ": x - y, " times ": x * y, " of ": x * y}[op]
        assert answer == expected
        if problem.skill == "integers":
            assert answer.denominator == 1
    elif problem.skill == "order_of_operations":
        if problem.level == 1:
            a, b, c = ints
            expected = a + b * c
        elif problem.level == 2:
            a, b, c, d = ints
            expected = (a + b) * c - d
        else:
            a, b, c, d = ints
            expected = a * b - c / d
        assert answer == expected and answer >= 0
    elif problem.skill == "equations":
        lhs, rhs = text.split(" equals ")
        n = [F(int(v)) for v in re.findall(r"\d+", lhs)]
        right, x = F(int(re.findall(r"\d+", rhs)[0])), answer
        if " times x plus " in lhs:
            assert n[0] * x + n[1] == right
        elif " times x" in lhs:
            assert n[0] * x == right
        elif "x plus" in lhs:
            assert x + n[0] == right
        else:
            assert x - n[0] == right
    else:
        assert problem.source.startswith("gsm8k-train-")
    assert parse_answer(problem.answer_text) == answer


@pytest.mark.parametrize("skill", list(SKILLS))
@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_problem_matches_its_answer(skill: str, level: int) -> None:
    """For each skill and level, 40 random problems read back to the stored answer and have helper steps."""
    rng = random.Random(f"{skill}{level}")
    for _ in range(40):
        problem = SKILLS[skill].generate(level, rng)
        assert problem.level == level and problem.steps and problem.explanation
        assert all(step.ask.endswith("?") for step in problem.steps)
        assert all(parse_answer(step.answer_text) == step.answer for step in problem.steps)
        _check_problem(problem)


def test_helper_steps_break_the_hard_part_into_small_questions() -> None:
    """75 times 9 becomes 70 times 9, 5 times 9, and 630 plus 45, in words a child knows."""
    problem = math_practice._multiply(1, random.Random(0))
    a, b = (int(n) for n in re.findall(r"\d+", problem.text))
    big, small = a // 10 * 10, a % 10
    assert [step.answer for step in problem.steps] == [big * b, small * b, a * b]
    assert problem.steps[0].ask.startswith(f"Let's break {a} into {big} and {small}.")
    words = " ".join([problem.explanation, *(step.ask for step in problem.steps)]).lower()
    assert not any(w in words for w in ("decompose", "distributive", "multiply each", "both sides"))


def test_word_problems_are_bundled_with_their_license() -> None:
    """300 GSM8K problems, 100 per level, with whole-number answers, helper steps, and the MIT notice."""
    rows = math_practice.word_problems()
    assert len(rows) == 300
    assert {level: sum(r["level"] == level for r in rows) for level in (1, 2, 3)} == {1: 100, 2: 100, 3: 100}
    assert all(isinstance(r["answer"], int) and len(r["question"].split()) <= 35 for r in rows)
    assert all(r["steps"] and all(s["ask"].endswith("?") for s in r["steps"]) for r in rows)
    first = math_practice._word_problem(1, random.Random(0)).steps[0].ask
    assert "What is" in first and not re.search(r"\d\s*[*/]\s*\d", first)  # said in words, not symbols
    notice = (math_practice.WORD_PROBLEMS_PATH.parent / "GSM8K_LICENSE.txt").read_text(encoding="utf-8")
    assert "MIT License" in notice and "OpenAI" in notice


def test_level_rule() -> None:
    """Three first-try answers in a row move up; two missed in a row move down; levels stay within 1 to 3."""
    p = SkillProgress()
    assert [record_result(p, "first_try") for _ in range(3)] == [0, 0, 1] and p.level == 2
    assert record_result(p, "first_try") == 0
    assert record_result(p, "with_help") == 0 and p.right_in_a_row == 0  # solving it with help resets the run
    assert [record_result(p, "missed") for _ in range(2)] == [0, -1] and p.level == 1
    assert [record_result(p, "missed") for _ in range(2)] == [0, 0] and p.level == 1
    for _ in range(9):
        record_result(p, "first_try")
    assert p.level == 3
    assert (p.problems, p.first_try_correct) == (18, 13)


def _answer_for(coach: MathCoach, wrong: bool = False) -> str:
    assert coach._open is not None
    answer = coach._open.problem.answer
    return math_practice.say_number(answer + 1 if wrong else answer)


def _step_answer(coach: MathCoach, wrong: bool = False) -> str:
    """Answer the helper question Reachy is asking now (a wrong answer is off by 1 from the step and the problem)."""
    open_problem = coach._open
    assert open_problem is not None and open_problem.step is not None
    answer = open_problem.problem.steps[open_problem.step].answer
    if wrong:
        answer += 1 if answer + 1 != open_problem.problem.answer else 2
    return math_practice.say_number(answer)


def test_a_wrong_answer_leads_to_small_helper_questions(study_dir: Path) -> None:
    """A miss gets the first helper question, not the answer; right helper answers end in 'with_help'."""
    study_log.start()
    coach = MathCoach(random.Random(1))
    asked = coach.next_problem()
    assert asked["problem_id"] == "M001" and asked["say"]
    assert coach._open is not None
    steps = coach._open.problem.steps

    first = coach.check_answer("I think it's 3")
    assert first["correct"] is False and first["close"] is False and "answer" not in first
    assert first["helper_question"] == steps[0].ask and "never say 'wrong'" in first["instructions"]
    for i in range(1, len(steps)):
        nxt = coach.check_answer(_step_answer(coach))
        assert nxt["correct"] is True and nxt["helper_question"] == steps[i].ask and "answer" not in nxt
    done = coach.check_answer(_step_answer(coach))
    assert done["correct"] is True and done["answer"] and done["explanation"]
    assert "step by step" in done["instructions"]
    assert coach.check_answer("5") == {"error": "No problem is open. Call next_math_problem first."}
    study_log.stop()

    events = [r for r in records(study_dir) if r.get("event", "").startswith("math_")]
    assert [e["event"] for e in events] == ["math_problem"] + ["math_answer"] * (len(steps) + 1)
    problem, a1, *_, last = events
    assert (problem["skill"], problem["level"], problem["asked_to"]) == ("multiply", 1, "unknown")
    assert (a1["attempt"], a1["step"], a1["correct"], a1["close"]) == (1, None, False, False)
    assert (last["step"], last["correct"], last["outcome"]) == (len(steps), True, "with_help")
    assert a1["heard"] and a1["parsed"] and a1["seconds_since_asked"] >= 0
    assert any(r["text"].startswith("math_answer") for r in csv_rows(study_dir))


def test_missed_helper_answers_are_given_and_count_as_missed(study_dir: Path) -> None:
    """A wrong helper answer is told kindly and the next one is asked; at the end the answer is explained."""
    study_log.start()
    coach = MathCoach(random.Random(1))
    coach.next_problem()
    assert coach._open is not None
    steps = coach._open.problem.steps
    coach.check_answer(_answer_for(coach, wrong=True))
    given = coach.check_answer(_step_answer(coach, wrong=True))
    assert given["correct"] is False and given["helper_answer"] == steps[0].answer_text
    assert given["helper_question"] == steps[1].ask
    while coach._open is not None and coach._open.step is not None and coach._open.step < len(steps) - 1:
        coach.check_answer(_step_answer(coach))
    end = coach.check_answer(_step_answer(coach))
    assert end["correct"] is True and "explanation" in end  # the child got the last step right ...
    study_log.stop()
    outcomes = [r.get("outcome") for r in records(study_dir) if r.get("event") == "math_answer"]
    assert outcomes[-1] == "missed"  # ... but Reachy had to give one answer away


def test_a_close_guess_is_praised_as_an_estimate() -> None:
    """75 times 9 answered 'around seven hundred' is close (within 10 percent), so Reachy says so."""
    coach = MathCoach(random.Random(1))
    coach.next_problem()
    assert coach._open is not None
    answer = coach._open.problem.answer
    near = math_practice.say_number(answer + max(1, answer // 20))
    result = coach.check_answer(f"probably around {near}?")
    assert result["close"] is True and "great estimate" in result["instructions"]


def test_jumping_straight_to_the_answer_during_help_counts(alice: Path) -> None:
    """A child who works it out after the first helper question is done, with help."""
    coach = MathCoach(random.Random(1))
    coach.next_problem()
    coach.check_answer(_answer_for(coach, wrong=True))
    done = coach.check_answer(_answer_for(coach))
    assert done["correct"] is True and coach._open is None
    assert coach._session_results == {"P01": ["with_help"]}


def test_saying_no_number_is_asked_again_but_i_dont_know_gets_help(study_dir: Path) -> None:
    """Mumbling gets 'say it as a number' and is not a try; 'I don't know' starts the helper questions."""
    study_log.start()
    coach = MathCoach(random.Random(2))
    coach.next_problem()
    unclear = coach.check_answer("um, wait")
    assert unclear["heard_a_number"] is False and "number" in unclear["instructions"]
    assert coach._open is not None and coach._open.attempts == 0
    stuck = coach.check_answer("I don't know")
    assert stuck["correct"] is False and stuck["helper_question"] == coach._open.problem.steps[0].ask
    assert "that's okay" in stuck["instructions"]
    study_log.stop()
    answers = [r for r in records(study_dir) if r.get("event") == "math_answer"]
    assert [(a["attempt"], a["correct"]) for a in answers] == [(None, None), (1, False)]


def test_right_on_the_first_try(study_dir: Path) -> None:
    """A right first answer is praised and logged as first_try."""
    study_log.start()
    coach = MathCoach(random.Random(2))
    coach.next_problem()
    right = coach.check_answer(f"is it {_answer_for(coach)}?")
    assert right["correct"] is True and "Praise" in right["instructions"] and "explanation" not in right
    study_log.stop()
    answers = [r for r in records(study_dir) if r.get("event") == "math_answer"]
    assert [(a["attempt"], a["outcome"]) for a in answers] == [(1, "first_try")]


@pytest.fixture
def alice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Voice ID says P01 (Alice) is speaking; people/ lives in tmp_path."""
    ident = SimpleNamespace(data_dir=tmp_path, name_of=lambda sid: "Alice" if sid == "P01" else "")
    monkeypatch.setattr(voice_id, "identifier", lambda: ident)
    monkeypatch.setattr(voice_id, "current_speaker", lambda: "P01")
    return tmp_path / "people" / "P01" / math_practice.PROGRESS_FILENAME


def test_progress_is_saved_per_child_and_levels_up(alice: Path) -> None:
    """Three right answers raise Alice's level; a new coach (next app run) picks it up from her file."""
    coach = MathCoach(random.Random(3))
    results = []
    for _ in range(3):
        coach.next_problem(topic="percent")
        results.append(coach.check_answer(_answer_for(coach)))
    assert results[-1]["level_change"] == "They move up to level 2 in percentages."
    saved = json.loads(alice.read_text(encoding="utf-8"))
    assert saved["current_skill"] == "percent" and saved["skills"]["percent"]["level"] == 2

    later = MathCoach(random.Random(4))
    assert later.next_problem()["level"] == 2


def test_after_five_problems_practice_moves_to_the_next_topic(alice: Path) -> None:
    """Without a requested topic, five problems on one skill are followed by the next skill."""
    coach = MathCoach(random.Random(5))
    topics = []
    for _ in range(6):
        topics.append(coach.next_problem()["topic"])
        coach.check_answer(_answer_for(coach))
    assert topics == ["multiplication"] * 5 + ["division"]


def test_unidentified_children_practice_without_a_saved_file(tmp_path: Path) -> None:
    """With no known speaker, nothing is written under people/."""
    coach = MathCoach(random.Random(6))
    coach.next_problem()
    coach.check_answer(_answer_for(coach))
    assert not (tmp_path / "people").exists()


def test_reachy_invites_again_three_minutes_after_the_greeting(alice: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The greeting is the first invitation; the note names the child and is not repeated right away."""
    monkeypatch.setenv(math_practice.MATH_ENV, "1")
    coach = MathCoach(random.Random(7))
    assert coach.offer_note_if_due(now=50.0) is None  # not connected yet
    coach.connection_opened(now=100.0)
    assert coach.offer_note_if_due(now=150.0) is None
    assert coach.offer_note_if_due(now=279.0) is None
    note = coach.offer_note_if_due(now=281.0)
    assert note is not None and note.startswith("Math practice:") and "Alice" in note and "math game" in note
    assert coach.offer_note_if_due(now=400.0) is None
    assert coach.offer_note_if_due(now=462.0) is not None

    coach.next_problem()
    assert coach.offer_note_if_due() is None  # practice under way
    coach.stop("done")
    assert coach.offer_note_if_due() is None  # just stopped: wait a full interval
    monkeypatch.setenv(math_practice.MATH_ENV, "0")
    assert coach.offer_note_if_due(now=10_000_000.0) is None


def test_stop_reports_each_childs_results(alice: Path) -> None:
    """Stopping returns how many problems each child did and how many were right on the first try."""
    coach = MathCoach(random.Random(8))
    coach.next_problem()
    coach.check_answer(_answer_for(coach))
    coach.next_problem()
    coach.check_answer(_answer_for(coach, wrong=True))
    assert coach.stop("child wants to play") == {
        "stopped": True,
        "results": {"P01": {"problems": 1, "first_try_correct": 1}},
    }


def test_tools_pass_through_to_the_coach(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model gets the problem text, then a verdict on the child's words."""
    monkeypatch.setattr(math_practice, "_coach", MathCoach(random.Random(9)))
    assert NextMathProblem().spec()["parameters"]["properties"]["topic"]["enum"] == list(SKILLS)
    asked = asyncio.run(NextMathProblem()(None, topic="equations"))  # type: ignore[arg-type]
    assert asked["topic"] == "equations" and asked["say"].startswith("If ")
    answer = _answer_for(math_practice.coach())
    checked = asyncio.run(CheckMathAnswer()(None, child_answer=f"x is {answer}"))  # type: ignore[arg-type]
    assert checked["correct"] is True
    assert "error" in asyncio.run(CheckMathAnswer()(None))  # type: ignore[arg-type]


def test_the_default_profile_greets_a_child_with_a_math_game(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reachy opens by inviting the child to a math game, in a child's words."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    greeting = prompts.get_session_greeting_prompt()
    assert "math game" in greeting and "10-year-old" in greeting
    assert "say hi and invite them to play a quick math game" in prompts.MATH_GUIDANCE


def test_prompt_explains_math_practice_only_when_it_is_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default profile has the math tools, so the guidance is added unless math is switched off."""
    monkeypatch.setattr(config, "REACHY_MINI_CUSTOM_PROFILE", None)
    monkeypatch.setenv(math_practice.MATH_ENV, "1")
    assert prompts.get_session_instructions(instance_path=tmp_path).startswith(prompts.MATH_GUIDANCE)
    monkeypatch.setenv(math_practice.MATH_ENV, "0")
    assert prompts.MATH_GUIDANCE not in prompts.get_session_instructions(instance_path=tmp_path)
