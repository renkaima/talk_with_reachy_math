"""Tests for the math games: story adventures, fixing Reachy's mistakes, number riddles, and closest guesses."""

import json
import random
import asyncio
from types import SimpleNamespace
from typing import Any
from pathlib import Path
from fractions import Fraction as F

import pytest
from study_helpers import records

from talk_with_reachy_math import voice_id, study_log, math_games, math_practice
from talk_with_reachy_math.math_practice import (
    GAMES,
    STORY,
    RIDDLES,
    CLOSEST_GUESS,
    FIX_MY_MISTAKE,
    MathCoach,
    numbers_in,
    parse_answer,
)
from talk_with_reachy_math.tools.math_practice import NextMathProblem


def _make(game: str, level: int, position: int, seed: int, theme: str = "space") -> math_practice.Problem:
    rng = random.Random(seed)
    turn = math_games.Turn(position, lambda _name: level, math_games.THEMES[theme], rng.randrange(1000), rng)
    return math_games.MAKERS[game](turn)


def _all(game: str) -> list[math_practice.Problem]:
    return [
        _make(game, level, position, seed, theme)
        for level in (1, 2, 3)
        for position in range(1, 6)
        for seed, theme in enumerate(math_games.THEMES)
    ]


@pytest.mark.parametrize("game", list(math_games.MAKERS))
def test_every_game_problem_has_its_helper_steps_right(game: str) -> None:
    """Helper questions end in a question mark and their answers read back; every game but guessing has them."""
    for problem in _all(game):
        assert problem.game == game and problem.text and problem.explanation
        assert bool(problem.steps) == (game != CLOSEST_GUESS)
        assert all(step.ask.endswith("?") and parse_answer(step.answer_text) == step.answer for step in problem.steps)
        assert parse_answer(problem.answer_text) == problem.answer


def test_story_parts_ask_what_their_numbers_say() -> None:
    """Each of the five parts is recomputed from the numbers in its text: pack, share, a part of, sale, count."""
    for problem in _all(STORY):
        n = numbers_in(problem.text)  # the story lines around the math have no numbers
        if "We pack" in problem.text:
            assert problem.answer == n[-2] * n[-1]
        elif "we meet" in problem.text:
            assert problem.answer == n[1] / n[0] and problem.answer.denominator == 1
        elif "we are stuck" in problem.text:
            assert problem.answer == n[0] * n[1] and problem.answer.denominator == 1
        elif "percent off" in problem.text:
            assert problem.answer == n[0] * n[1] / 100
        else:
            assert problem.text.startswith("Last stop!") and problem.answer == n[2] + n[0] * n[1]
        assert problem.theme in math_games.THEMES


def test_reachy_makes_a_real_mistake_and_says_what_it_was() -> None:
    """Reachy's answer is wrong, appears in the text, and the explanation starts with the mistake."""
    kinds = set()
    for problem in _all(FIX_MY_MISTAKE):
        assert problem.reachy_answer is not None and problem.reachy_answer != problem.answer
        assert problem.text.startswith("Can you check my work?") and problem.explanation.startswith("My mistake:")
        kinds.add(problem.skill)
    assert kinds == {"fractions", "order_of_operations", "multiply", "decimals", "integers", "percent", "equations"}


def test_a_round_of_mistakes_has_five_different_ones() -> None:
    """Within one round, each problem shows a different kind of mistake."""
    rng = random.Random(3)
    start = rng.randrange(1000)
    theme = math_games.THEMES["dogs"]
    skills = [
        math_games.MAKERS[FIX_MY_MISTAKE](math_games.Turn(position, lambda _name: 1, theme, start, rng)).skill
        for position in range(1, 6)
    ]
    assert len(set(skills)) == 5


def test_every_riddle_has_exactly_one_answer() -> None:
    """Only the secret number fits all the clues, and a wrong guess is told which clue it breaks."""
    for problem in _all(RIDDLES):
        lo, hi = (int(v) for v in numbers_in(problem.clues[0].text))
        fits = [n for n in range(lo - 5, hi + 6) if all(clue.fits(n) for clue in problem.clues)]
        assert fits == [problem.answer] and 3 <= len(problem.clues) <= 4
    problem = _make(RIDDLES, 1, 1, 0)
    assert math_games.riddle_miss(problem, F(int(problem.answer) + 1)) is not None
    assert math_games.riddle_miss(problem, F(3, 2)) == "My number is a whole number."


def test_closest_guess_numbers_are_near_round_ones() -> None:
    """The answer is the product in the text; Reachy's guess is off by a fifth or a quarter."""
    for problem in _all(CLOSEST_GUESS):
        b, a = numbers_in(problem.text)[:2]
        assert problem.answer == a * b
        assert problem.reachy_answer is not None
        off = abs(problem.reachy_answer - problem.answer) / problem.answer
        assert F(1, 10) < off < F(1, 3)


# ---------------------------------------------------------------------------
# Playing the games with the coach


def _start(coach: MathCoach, **kwargs: Any) -> dict[str, Any]:
    """Start a round; the first time a child plays a game, Reachy tells the rules before the first problem."""
    asked = coach.next_problem(**kwargs)
    if "problem_id" not in asked:
        assert asked["how_to_play"] and coach._open is None
        asked = coach.next_problem()
    return asked


def _right(coach: MathCoach) -> str:
    assert coach._open is not None
    return math_practice.say_number(coach._open.problem.answer)


def test_a_story_round_goes_on_part_by_part_and_ends_the_story(study_dir: Path) -> None:
    """The story is read part after part, then the ending is read and the child picks the next game."""
    study_log.start()
    coach = MathCoach(random.Random(1))
    rules = coach.next_problem(game=STORY, theme="dinosaurs")
    assert rules["game"] == "a story adventure" and "story adventure in 5 parts" in rules["instructions"]
    assert rules["how_to_play"] == math_games.HOW_TO_PLAY[STORY]
    asked = coach.next_problem()
    assert asked["say"].startswith("We are going to look for dinosaur eggs!")
    results = []
    for position in range(5):
        if position:
            coach.next_problem()  # the child says they are ready
        results.append(coach.check_answer(_right(coach)))
    assert all("ready for the next part of the story" in r["instructions"] for r in results[:4])
    end = results[4]
    assert end["story_end"] == math_games.THEMES["dinosaurs"].end and end["story_end"] in end["instructions"]
    assert "pick the next game" in end["instructions"] and coach._game is None
    study_log.stop()
    problems = [r for r in records(study_dir) if r.get("event") == "math_problem"]
    assert {(p["game"], p["theme"]) for p in problems} == {(STORY, "dinosaurs")}
    assert [p["skill"] for p in problems] == ["multiply", "divide", "fractions", "percent", "order_of_operations"]


def test_fixing_reachys_mistake(study_dir: Path) -> None:
    """Saying Reachy's own wrong answer starts the check together; a right fix leads to 'What did I do wrong?'."""
    study_log.start()
    coach = MathCoach(random.Random(2))
    _start(coach, game=FIX_MY_MISTAKE)
    assert coach._open is not None
    problem = coach._open.problem
    no = coach.check_answer("No, that's not right!")
    assert no["heard_a_number"] is False and "real answer" in no["instructions"]
    assert problem.reachy_answer is not None
    same = coach.check_answer(math_practice.say_number(problem.reachy_answer))
    assert "got that answer too" in same["instructions"] and same["try_again"] is True
    together = coach.check_answer(math_practice.say_number(problem.reachy_answer))
    assert "got that answer too" in together["instructions"] and together["helper_question"] == problem.steps[0].ask
    coach.stop("test")
    _start(coach, game=FIX_MY_MISTAKE)
    fixed = coach.check_answer(_right(coach))
    assert (
        "What did I do wrong?" in fixed["instructions"]
        and "After you thank them, ask if they are ready" in fixed["instructions"]
    )
    study_log.stop()
    asked = [r for r in records(study_dir) if r.get("event") == "math_problem"]
    assert asked[0]["reachy_answer"] == math_practice.say_number(problem.reachy_answer)


def test_a_wrong_riddle_guess_hears_which_clue_it_breaks(study_dir: Path) -> None:
    """A wrong guess hears the clue it does not fit and tries again; a second wrong guess gets one more clue."""
    study_log.start()
    coach = MathCoach(random.Random(4))
    _start(coach, game=RIDDLES)
    assert coach._open is not None
    secret = int(coach._open.problem.answer)
    result = coach.check_answer(f"is it {secret + 1}?")
    assert result["correct"] is False and result["close"] is False and result["try_again"] is True
    assert result["clue_missed"].startswith(f"{secret + 1}") and result["clue_missed"] in result["instructions"]
    assert "helper_question" not in result
    again = coach.check_answer(f"{secret + 1}")
    assert again["helper_question"].startswith("Here is one more clue.")
    study_log.stop()
    answers = [r for r in records(study_dir) if r.get("event") == "math_answer"]
    assert answers[0]["clue_missed"] == result["clue_missed"]


def test_closest_guess_compares_the_guesses(study_dir: Path) -> None:
    """Any number is a guess; Reachy then says its own guess and the real answer, and the closer one wins."""
    study_log.start()
    coach = MathCoach(random.Random(5))
    _start(coach, game=CLOSEST_GUESS)
    assert coach._open is not None
    problem = coach._open.problem
    assert coach.check_answer("I don't know")["heard_a_number"] is False  # a guess is needed, not help
    won = coach.check_answer(math_practice.say_number(problem.answer + 1))
    assert won["winner"] == "child" and won["correct"] is True and won["reachy_guess"] in won["instructions"]
    assert "they win this one" in won["instructions"] and "ready for the next one" in won["instructions"]
    coach.next_problem()
    assert coach._open is not None
    reachy = coach._open.problem.reachy_answer
    assert reachy is not None
    lost = coach.check_answer(math_practice.say_number(coach._open.problem.answer * 3))
    assert lost["winner"] == "reachy" and lost["correct"] is False
    study_log.stop()
    answers = [r for r in records(study_dir) if r.get("event") == "math_answer" and r.get("winner")]
    assert [(a["winner"], a["outcome"]) for a in answers] == [("child", "first_try"), ("reachy", "with_help")]


def test_every_game_is_offered_within_three_rounds() -> None:
    """Offers rotate through the five games, two at a time."""
    coach = MathCoach(random.Random(6))
    offered = set(coach._offered)
    for _ in range(2):
        coach._offered = coach._next_offer()
        offered |= set(coach._offered)
    assert offered == set(GAMES)


def test_the_child_can_switch_games_mid_round() -> None:
    """Picking another game starts a new round of it; the same game keeps the round going."""
    coach = MathCoach(random.Random(7))
    _start(coach, game=RIDDLES)
    coach.check_answer(_right(coach))
    assert coach._round_count == 1 and coach.next_problem(game=RIDDLES)["round_position"] == "2 of 5"
    switched = _start(coach, game=CLOSEST_GUESS)
    assert switched["round_position"] == "1 of 5" and coach._rounds == 2


@pytest.fixture
def alice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Voice ID says P01 (Alice) is speaking; people/ lives in tmp_path."""
    ident = SimpleNamespace(data_dir=tmp_path, name_of=lambda sid: "Alice" if sid == "P01" else "")
    monkeypatch.setattr(voice_id, "identifier", lambda: ident)
    monkeypatch.setattr(voice_id, "current_speaker", lambda: "P01")
    return tmp_path / "people" / "P01" / math_practice.PROGRESS_FILENAME


def test_what_a_child_likes_is_saved_for_next_time(alice: Path) -> None:
    """A theme picked once is saved in the child's file and used by the next story, even after a restart."""
    coach = MathCoach(random.Random(8))
    _start(coach, game=STORY, theme="soccer")
    assert json.loads(alice.read_text(encoding="utf-8"))["theme"] == "soccer"
    later = MathCoach(random.Random(9))
    asked = later.next_problem(game=STORY)  # the rules were told last time, so the story starts right away
    assert asked["say"].startswith(math_games.THEMES["soccer"].start) and asked["reminder"]
    riddle_level = later._learner("P01").skill(RIDDLES)
    assert riddle_level.level == 1  # games with their own level start at 1


def test_the_tool_offers_games_and_themes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model can name a game and a theme; quick math still takes a topic."""
    monkeypatch.setattr(math_practice, "_coach", MathCoach(random.Random(10)))
    props = NextMathProblem().spec()["parameters"]["properties"]
    assert props["game"]["enum"] == list(GAMES) and props["theme"]["enum"] == list(math_games.THEMES)
    rules = asyncio.run(NextMathProblem()(None, game=RIDDLES))  # type: ignore[arg-type]
    assert rules["game"] == "number riddles" and rules["how_to_play"] == math_games.HOW_TO_PLAY[RIDDLES]
    asked = asyncio.run(NextMathProblem()(None, game=RIDDLES))  # type: ignore[arg-type]
    assert asked["game"] == "number riddles" and asked["say"].startswith("I'm thinking of a number")


def test_every_game_has_rules_and_a_reminder() -> None:
    """Each game has rules for the first time and a one-line reminder for later."""
    assert set(math_games.HOW_TO_PLAY) == set(math_games.REMINDERS) == set(GAMES)
    assert all(text.startswith("Here is how it works.") for text in math_games.HOW_TO_PLAY.values())
