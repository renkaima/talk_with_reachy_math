"""Spoken math practice for children aged about 10 to 13 (US grades 5 to 7).

Problems are generated and checked here in code. The conversation model only reads a
problem aloud and passes on what the child said, so the answer Reachy confirms is always
computed, never guessed by the model.

Practice runs in rounds of five problems from one game. At the start of each round the
child picks one of two games; ``math_games`` builds the problems of the story, mistake,
riddle, and guessing games, and this module builds the quick math problems (one topic at
a time) and runs the rounds.

The first time a child plays a game, Reachy reads its rules before the first problem; later
rounds of the same game get a one-line reminder. After each problem, Reachy asks whether the
child is ready, and the next problem is opened only when the model asks for it.

When a child's first answer is not right (or they say they don't know), Reachy asks them to
think again, without a hint. After a second answer that is not right, or as soon as the child
asks for help, Reachy asks the problem's helper steps instead of giving a long hint: small
questions such as "What is 70 times 9?", one at a time, each checked here too.

Each child has a level from 1 to 3 per skill (and per game for riddles and guessing), kept
in ``people/<speaker_id>/math_progress.json`` and found through voice ID. Levels follow a
fixed rule: three problems in a row answered correctly on the first try move the child up
one level; two problems in a row in which Reachy had to give away an answer (of a helper
step or of the problem) move them down one level. A problem solved on the second try, or with
help with every helper step answered right, leaves the level alone and resets both counts.

Every problem, answer, and level change is written to the study log as an event.
"""

from __future__ import annotations
import os
import re
import json
import math
import time
import random
import logging
import threading
from typing import Any
from decimal import Decimal
from pathlib import Path
from fractions import Fraction
from dataclasses import field, asdict, dataclass
from collections.abc import Callable

from talk_with_reachy_math import voice_id, study_log
from talk_with_reachy_math.voice_files import UNKNOWN, person_dir


logger = logging.getLogger(__name__)

MATH_ENV = "TALK_WITH_REACHY_MATH_PRACTICE"
OFFER_AFTER_ENV = "TALK_WITH_REACHY_MATH_OFFER_AFTER_S"
DEFAULT_OFFER_AFTER_S = 180.0  # the greeting is the first invitation; this is the wait before the next
PRACTICE_IDLE_S = 600.0  # practice counts as over after this long without a math tool call
PROGRESS_FILENAME = "math_progress.json"

MIN_LEVEL, MAX_LEVEL = 1, 3
LEVEL_UP_AFTER = 3  # first-try correct answers in a row
LEVEL_DOWN_AFTER = 2  # problems in a row in which Reachy gave away an answer
PROBLEMS_PER_SKILL = 5  # then the next problem without a topic moves on to the next skill
ROUND_SIZE = 5  # problems Reachy asks one after another before offering a break
# Games, as the next_math_problem tool names them. math_games builds all but quick math.
STORY, FIX_MY_MISTAKE, RIDDLES, CLOSEST_GUESS, QUICK_MATH = (
    "story",
    "fix_my_mistake",
    "riddles",
    "closest_guess",
    "quick_math",
)
GAMES = (STORY, FIX_MY_MISTAKE, RIDDLES, CLOSEST_GUESS, QUICK_MATH)  # also the order in which they are offered
STEER_AFTER_TURNS = (2, 5)  # turns in a row without math after which Reachy is told to steer back
CLOSE_ENOUGH = Fraction(1, 10)  # a first answer this close (relative) is praised as a good estimate
# Words that mean "I need help" or "I'm stuck" when a child says no number; anything else is asked
# again. A child who asks for a hint gets a helper question right away; a child who only says they
# are stuck is first given time to think (docs/LEARNING_DESIGN.md, section 7, explains why).
_ASKS_FOR_HELP = re.compile(r"\b(help|hint|give up)\b", re.IGNORECASE)
_FEELS_STUCK = re.compile(r"\b(don'?t know|dunno|no idea|not sure|hard|stuck|confus\w*)\b", re.IGNORECASE)


def enabled() -> bool:
    """Return whether math practice is on (it is unless the env var is 0)."""
    return os.getenv(MATH_ENV, "1").strip() != "0"


def offer_after_s() -> float:
    """Seconds after the last invitation to a math game (or the end of practice) before Reachy invites again."""
    try:
        return float(os.getenv(OFFER_AFTER_ENV) or DEFAULT_OFFER_AFTER_S)
    except ValueError:
        return DEFAULT_OFFER_AFTER_S


# ---------------------------------------------------------------------------
# Saying numbers


_DENOMINATOR_WORDS = {
    2: ("half", "halves"),
    3: ("third", "thirds"),
    4: ("fourth", "fourths"),
    5: ("fifth", "fifths"),
    6: ("sixth", "sixths"),
    7: ("seventh", "sevenths"),
    8: ("eighth", "eighths"),
    9: ("ninth", "ninths"),
    10: ("tenth", "tenths"),
    11: ("eleventh", "elevenths"),
    12: ("twelfth", "twelfths"),
    15: ("fifteenth", "fifteenths"),
    16: ("sixteenth", "sixteenths"),
    20: ("twentieth", "twentieths"),
    24: ("twenty-fourth", "twenty-fourths"),
    30: ("thirtieth", "thirtieths"),
    40: ("fortieth", "fortieths"),
    60: ("sixtieth", "sixtieths"),
    100: ("hundredth", "hundredths"),
}


def _proper_fraction_words(numerator: int, denominator: int) -> str:
    names = _DENOMINATOR_WORDS.get(denominator)
    if names is None:
        return f"{numerator} over {denominator}"
    return f"{numerator} {names[0] if numerator == 1 else names[1]}"


def say_fraction(value: Fraction) -> str:
    """Words for a fraction as a child would say it: ``2 thirds``, ``1 and 1 half``, ``negative 3 fourths``."""
    sign = "negative " if value < 0 else ""
    value = abs(value)
    whole, rest = divmod(value.numerator, value.denominator)
    if rest == 0:
        return f"{sign}{whole}"
    part = _proper_fraction_words(rest, value.denominator)
    return f"{sign}{whole} and {part}" if whole else f"{sign}{part}"


def say_decimal(value: Fraction) -> str:
    """Write a terminating fraction as a decimal, such as ``3.45``."""
    text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def say_number(value: Fraction) -> str:
    """Integers as digits, terminating non-integers as decimals, everything else as a fraction."""
    if value.denominator == 1:
        return f"negative {-value.numerator}" if value < 0 else str(value.numerator)
    if _terminates(value):
        return f"negative {say_decimal(-value)}" if value < 0 else say_decimal(value)
    return say_fraction(value)


def _terminates(value: Fraction) -> bool:
    d = value.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    return d == 1


def _signed(n: int) -> str:
    return f"negative {-n}" if n < 0 else str(n)


# ---------------------------------------------------------------------------
# Hearing numbers

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_HEARD_DENOMINATORS = {
    "half": 2,
    "halves": 2,
    "quarter": 4,
    "quarters": 4,
    **{name: d for d, names in _DENOMINATOR_WORDS.items() for name in names if "-" not in name},
}
_NEGATIVE_WORDS = {"negative", "minus"}
_TOKEN = re.compile(r"\d+/\d+|\d*\.\d+|\d+|[a-z]+|/")


def _tokens(text: str) -> list[str]:
    text = text.lower().replace("−", "-")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,200 -> 1200
    text = re.sub(r"(?<![\w.])-(?=\.?\d)", " negative ", text)  # -5 -> negative 5
    text = text.replace("%", " percent ").replace("$", " ")
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)  # twenty-three -> twenty three
    return _TOKEN.findall(text)


def _is_number_word(tok: str) -> bool:
    return tok in _UNITS or tok in _TENS or tok in _SCALES


def _read_words(toks: list[str], i: int) -> tuple[int, int] | None:
    """Read an English cardinal such as ``three hundred and five`` starting at ``toks[i]``.

    Words must follow English number order, so ``twenty five twenty fourths`` stops after
    ``twenty five`` and leaves ``twenty fourths`` to be read as a denominator.
    """
    total = current = 0
    j = i
    last = ""  # kind of the previous word: "", "unit" (1-9), "teen" (0, 10-19), "tens", or "scale"
    while j < len(toks):
        tok = toks[j]
        if tok in _UNITS:
            kind = "unit" if 0 < _UNITS[tok] < 10 else "teen"
            if last not in ("", "scale") and not (last == "tens" and kind == "unit"):
                break
            current += _UNITS[tok]
        elif tok in _TENS:
            if last not in ("", "scale"):
                break
            kind = "tens"
            current += _TENS[tok]
        elif tok in _SCALES and last:
            kind = "scale"
            if _SCALES[tok] == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * _SCALES[tok]
                current = 0
        elif (
            tok == "and"
            and last == "scale"
            and j + 1 < len(toks)
            and (toks[j + 1] in _UNITS or toks[j + 1] in _TENS)
            and not (j + 2 < len(toks) and toks[j + 2] in _HEARD_DENOMINATORS)
        ):
            j += 1  # "one hundred and five"
            continue
        else:
            break
        last = kind
        j += 1
    return (total + current, j) if last else None


def _read_plain(toks: list[str], i: int) -> tuple[Fraction, int] | None:
    """Read a number without sign or fraction words: digits, ``3/4``, a cardinal, or ``a`` before a scale."""
    tok = toks[i]
    if re.fullmatch(r"\d+/\d+", tok):
        num, den = (int(x) for x in tok.split("/"))
        return (Fraction(num, den), i + 1) if den else None
    if re.fullmatch(r"\d*\.\d+|\d+", tok):
        value = Fraction(Decimal(tok))
        j = i + 1
        while j < len(toks) and toks[j] in _SCALES:  # "3 thousand"
            value *= _SCALES[toks[j]]
            j += 1
        return value, j
    if tok == "a" and i + 1 < len(toks) and toks[i + 1] in _SCALES:
        words = _read_words(["one", *toks[i + 1 :]], 0)
        return (Fraction(words[0]), i + words[1]) if words else None
    if _is_number_word(tok) and tok not in _SCALES:
        words = _read_words(toks, i)
        return (Fraction(words[0]), words[1]) if words else None
    return None


def _read_decimal_tail(toks: list[str], j: int, value: Fraction) -> tuple[Fraction, int]:
    """``two point five`` / ``two point two five``: digits after ``point`` read one by one."""
    if j + 1 >= len(toks) or toks[j] != "point":
        return value, j
    digits = ""
    k = j + 1
    while k < len(toks):
        tok = toks[k]
        if tok.isdigit():
            digits += tok
        elif tok in _UNITS and _UNITS[tok] < 10:
            digits += str(_UNITS[tok])
        else:
            break
        k += 1
    if not digits:
        return value, j
    return value + Fraction(int(digits), 10 ** len(digits)), k


def _read_fraction_tail(toks: list[str], j: int, value: Fraction) -> tuple[Fraction, int]:
    """``3 fourths``, ``three over four``, ``3 out of 4`` after a whole number."""
    if value.denominator != 1 or j >= len(toks):
        return value, j
    if toks[j] in _HEARD_DENOMINATORS:
        return value / _HEARD_DENOMINATORS[toks[j]], j + 1
    if toks[j] in _TENS and j + 1 < len(toks) and _HEARD_DENOMINATORS.get(toks[j + 1], 10) < 10:
        return value / (_TENS[toks[j]] + _HEARD_DENOMINATORS[toks[j + 1]]), j + 2  # "twenty fourths"
    over = 2 if toks[j : j + 2] == ["out", "of"] else 1 if toks[j] in ("over", "/") else 0
    if over and j + over < len(toks):
        den = _read_plain(toks, j + over)
        if den is not None and den[0] != 0:
            return value / den[0], den[1]
    return value, j


def _read_number(toks: list[str], i: int) -> tuple[Fraction, int] | None:
    sign = 1
    j = i
    if toks[j] in _NEGATIVE_WORDS and j + 1 < len(toks):
        sign, j = -1, j + 1
    if toks[j] in ("a", "one") and j + 1 < len(toks) and toks[j + 1] in _HEARD_DENOMINATORS:
        return sign * Fraction(1, _HEARD_DENOMINATORS[toks[j + 1]]), j + 2  # "a half", "one third"
    plain = _read_plain(toks, j)
    if plain is None:
        return None
    value, j = plain
    value, j = _read_decimal_tail(toks, j, value)
    value, j = _read_fraction_tail(toks, j, value)
    # Mixed number: "2 and a half", "two and 3 fourths".
    if value.denominator == 1 and j + 1 < len(toks) and toks[j] == "and":
        part = _read_number(toks, j + 1)
        if part is not None and 0 < part[0] < 1:
            value, j = value + part[0], part[1]
    return sign * value, j


def numbers_in(text: str) -> list[Fraction]:
    """Every number in ``text``, in order: digits, words, decimals, fractions, mixed numbers, negatives."""
    toks = _tokens(text)
    found: list[Fraction] = []
    i = 0
    while i < len(toks):
        read = _read_number(toks, i)
        if read is None:
            i += 1
            continue
        found.append(read[0])
        i = max(read[1], i + 1)
    return found


def parse_answer(text: str) -> Fraction | None:
    """Return the child's answer: the last number they said, or None if they said no number."""
    found = numbers_in(text)
    return found[-1] if found else None


def answer_matches(heard: Fraction, answer: Fraction) -> bool:
    """Exact match, or a decimal that rounds the answer correctly to the places the child said."""
    if heard == answer:
        return True
    places = 0
    d = heard.denominator
    while d % 10 == 0:
        d //= 10
        places += 1
    if d != 1 or places < 2 or _terminates(answer):
        return False
    return round(answer, places) == heard


# ---------------------------------------------------------------------------
# Problems


@dataclass(frozen=True)
class Step:
    """A small helper question Reachy asks when a child needs help; its answer is checked in code too."""

    ask: str
    answer: Fraction
    also: Fraction | None = None  # another answer that means the same, such as "9 twelfths" for "9"

    def matches(self, heard: Fraction) -> bool:
        """Whether ``heard`` answers this helper question."""
        return answer_matches(heard, self.answer) or heard == self.also

    @property
    def answer_text(self) -> str:
        """How Reachy says the helper answer."""
        return say_number(self.answer)


@dataclass(frozen=True)
class Clue:
    """One clue of a number riddle, such as "It is odd.", and how to test a guess against it."""

    text: str
    fits: Callable[[int], bool]
    because: str  # why the secret number fits, said in the explanation: "27 is odd"


@dataclass(frozen=True)
class Problem:
    """One problem, as Reachy should read it, with its helper steps and a child-friendly explanation.

    ``skill`` is also the key of the child's level for it: a topic such as ``fractions``, or
    ``riddles`` and ``closest_guess`` for those games.
    """

    skill: str
    level: int
    text: str
    answer: Fraction
    steps: tuple[Step, ...]
    explanation: str
    source: str = "generated"
    game: str = QUICK_MATH
    reachy_answer: Fraction | None = None  # Reachy's wrong answer (fix my mistake) or its guess (closest guess)
    clues: tuple[Clue, ...] = ()  # riddles: every clue, the range first
    theme: str = ""  # what the story or guessing problem is about, such as "space"

    @property
    def answer_text(self) -> str:
        """How Reachy says the answer: fractions as fractions, other answers as numbers."""
        return say_fraction(self.answer) if self.skill == "fractions" else say_number(self.answer)


Generator = Callable[[int, random.Random], Problem]


def multiply_numbers(level: int, rng: random.Random) -> tuple[int, int]:
    """Pick the two numbers of a multiplication problem at ``level``; the second is the smaller."""
    a = (
        rng.choice([n for n in range(101, 1000) if n % 10])
        if level == 3
        else rng.choice([n for n in range(12, 100) if n % 10])
    )
    b = rng.randint(3, 9) if level == 1 else rng.choice([n for n in range(11, 100) if n % 10])
    return a, b


def _multiply(level: int, rng: random.Random) -> Problem:
    return multiply_problem(level, *multiply_numbers(level, rng))


def multiply_problem(level: int, a: int, b: int) -> Problem:
    """Build ``a`` times ``b``, with helper steps that break one number into tens and ones."""
    if b < 10:  # break the bigger number into tens and ones
        big, small = a // 10 * 10, a % 10
        steps = (
            Step(f"Let's break {a} into {big} and {small}. What is {big} times {b}?", Fraction(big * b)),
            Step(f"Now, what is {small} times {b}?", Fraction(small * b)),
            Step(f"Last step: what is {big * b} plus {small * b}?", Fraction(a * b)),
        )
        explanation = (
            f"{a} is {big} plus {small}. {big} times {b} is {big * b}, and {small} times {b} is {small * b}. "
            f"{big * b} plus {small * b} makes {a * b}."
        )
    else:
        big, small = b // 10 * 10, b % 10
        steps = (
            Step(
                f"Let's break {b} into {big} and {small}. Here's a tip: do {a} times {big // 10}, then put a zero "
                f"on the end. What is {a} times {big}?",
                Fraction(a * big),
            ),
            Step(f"Now, what is {a} times {small}?", Fraction(a * small)),
            Step(f"Last step: what is {a * big} plus {a * small}?", Fraction(a * b)),
        )
        explanation = (
            f"{b} is {big} plus {small}. {a} times {big} is {a * big}, and {a} times {small} is {a * small}. "
            f"{a * big} plus {a * small} makes {a * b}."
        )
    return Problem("multiply", level, f"What is {a} times {b}?", Fraction(a * b), steps, explanation)


def divide_numbers(level: int, rng: random.Random) -> tuple[int, int]:
    """Pick the answer and the divisor of a division problem at ``level``."""
    if level == 1:
        return rng.randint(12, 99), rng.randint(3, 9)
    if level == 2:
        return rng.randint(11, 39), rng.randint(11, 25)
    return rng.randint(21, 99), rng.randint(12, 49)


def _divide(level: int, rng: random.Random) -> Problem:
    return divide_problem(level, *divide_numbers(level, rng))


def divide_problem(level: int, q: int, d: int) -> Problem:
    """``q`` times ``d`` divided by ``d``, with helper steps that take away a round number of groups first."""
    n = q * d
    tens = q // 10 * 10
    if q == tens:
        steps: tuple[Step, ...] = (
            Step(f"Let's use a times fact. {d} times what number makes {n // 10}?", Fraction(q // 10)),
            Step(f"So {d} times {q // 10} tens makes {n}. How much is {q // 10} tens?", Fraction(q)),
        )
        explanation = f"{d} times {q} is {n}, so {n} divided by {d} is {q}."
    else:
        rest = n - d * tens
        steps = (
            Step(
                f"Let's do it in two pieces. {d} times {tens} is {d * tens}. What is {n} minus {d * tens}?",
                Fraction(rest),
            ),
            Step(f"Now, {d} times what number makes {rest}?", Fraction(q - tens)),
            Step(f"Last step: what is {tens} plus {q - tens}?", Fraction(q)),
        )
        explanation = (
            f"{d} times {tens} is {d * tens}, and {d} times {q - tens} is {rest}. "
            f"Together, {d} times {q} makes {n}, so {n} divided by {d} is {q}."
        )
    return Problem("divide", level, f"What is {n} divided by {d}?", Fraction(q), steps, explanation)


_NICE_DENOMINATORS = (2, 3, 4, 5, 6, 8, 10, 12)


def _same_as(value: Fraction, said: str) -> str:
    """', which is the same as 3 fourths' when the answer can be said more simply."""
    simpler = say_fraction(value)
    return "" if simpler == said else f", which is the same as {simpler}"


def fraction_steps(x: Fraction, y: Fraction, op: str) -> tuple[tuple[Step, ...], str]:
    """Build the helper steps and explanation for ``x`` plus or minus ``y``: same bottom numbers first."""
    common = math.lcm(x.denominator, y.denominator)
    unit = _DENOMINATOR_WORDS[common][1]
    k1, k2 = (f.numerator * common // f.denominator for f in (x, y))
    k = k1 + k2 if op == "plus" else k1 - k2
    value = x + y if op == "plus" else x - y
    steps: list[Step] = []
    for f, kf in ((x, k1), (y, k2)):
        if f.denominator != common:
            intro = "" if steps else f"Let's make the bottom numbers the same. {common} works for both. "
            steps.append(Step(f"{intro}{say_fraction(f)} is how many {unit}?", Fraction(kf), also=f))
    steps.append(Step(f"Now {op} the top numbers. What is {k1} {op} {k2}?", Fraction(k)))
    total = _proper_fraction_words(k, common)
    same_bottom = ", and ".join(
        f"{say_fraction(f)} is {_proper_fraction_words(kf, common)}"
        for f, kf in ((x, k1), (y, k2))
        if f.denominator != common
    )
    return (
        tuple(steps),
        f"Let's make the bottom numbers the same. {same_bottom}. {k1} {op} {k2} is {k}. So the answer is {total}"
        f"{_same_as(value, total)}.",
    )


def fraction_of_problem(level: int, x: Fraction, whole: int) -> Problem:
    """``x`` of ``whole``: first find one part, then take as many parts as the top number says."""
    d = x.denominator
    value = x * whole
    one = _DENOMINATOR_WORDS[d][0]
    steps = [Step(f"First find 1 {one} of {whole}. What is {whole} divided by {d}?", Fraction(whole // d))]
    if x.numerator > 1:
        steps.append(Step(f"We need {x.numerator} of those. What is {x.numerator} times {whole // d}?", value))
    return Problem(
        "fractions",
        level,
        f"What is {say_fraction(x)} of {whole}?",
        value,
        tuple(steps),
        f"1 {one} of {whole} is {whole} divided by {d}, which is {whole // d}."
        + (f" {x.numerator} of those make {say_number(value)}." if x.numerator > 1 else ""),
    )


def _fractions(level: int, rng: random.Random) -> Problem:
    if level == 1:
        d = rng.randint(5, 12)
        a = rng.randint(1, d - 2)
        b = rng.randint(1, d - 1 - a)
        x, y = Fraction(a, d), Fraction(b, d)
        unit = _DENOMINATOR_WORDS[d][1]
        total = _proper_fraction_words(a + b, d)
        return Problem(
            "fractions",
            level,
            f"What is {_proper_fraction_words(a, d)} plus {_proper_fraction_words(b, d)}?",
            x + y,
            (
                Step(
                    f"The bottom numbers are both {d}, so the answer is in {unit}. "
                    f"We just add the top numbers. What is {a} plus {b}?",
                    Fraction(a + b),
                ),
            ),
            f"The bottom numbers are the same, so we add the top numbers. {a} plus {b} is {a + b}. "
            f"That makes {total}{_same_as(x + y, total)}.",
        )
    if level == 2:
        d1, d2 = rng.sample(_NICE_DENOMINATORS, 2)
        x = Fraction(rng.randint(1, d1 - 1), d1)
        y = Fraction(rng.randint(1, d2 - 1), d2)
        if rng.random() < 0.5 or x == y:
            op, value = "plus", x + y
        else:
            x, y = max(x, y), min(x, y)
            op, value = "minus", x - y
        steps, explanation = fraction_steps(x, y, op)
        return Problem(
            "fractions", level, f"What is {say_fraction(x)} {op} {say_fraction(y)}?", value, steps, explanation
        )
    if rng.random() < 0.5:
        d = rng.choice(_NICE_DENOMINATORS[1:])
        return fraction_of_problem(level, Fraction(rng.randint(1, d - 1), d), d * rng.randint(2, 9))
    d1, d2 = rng.sample(_NICE_DENOMINATORS, 2)
    x = Fraction(rng.randint(1, d1 - 1), d1)
    y = Fraction(rng.randint(1, d2 - 1), d2)
    value = x * y
    top, bottom = x.numerator * y.numerator, x.denominator * y.denominator
    total = _proper_fraction_words(top, bottom)
    return Problem(
        "fractions",
        level,
        f"What is {say_fraction(x)} times {say_fraction(y)}?",
        value,
        (
            Step(
                f"To multiply fractions, multiply the top numbers. What is {x.numerator} times {y.numerator}?",
                Fraction(top),
            ),
            Step(f"Now multiply the bottom numbers. What is {x.denominator} times {y.denominator}?", Fraction(bottom)),
        ),
        f"Top times top is {top}. Bottom times bottom is {bottom}. So the answer is {total}{_same_as(value, total)}.",
    )


def _decimals(level: int, rng: random.Random) -> Problem:
    def tenths(lo: int, hi: int) -> Fraction:
        return Fraction(rng.randint(lo, hi), 10)

    if level == 3:
        if rng.random() < 0.5:
            x, y = tenths(2, 19), Fraction(rng.randint(3, 9))
        else:
            x, y = tenths(11, 49), tenths(2, 9)
        value = x * y
        whole_x, whole_y = x * 10, y if y.denominator == 1 else y * 10
        product = whole_x * whole_y
        places = 1 if y.denominator == 1 else 2
        digits = (
            f"{say_number(x)} has 1 digit after the point. So the answer needs 1 digit after the point too."
            if places == 1
            else f"{say_number(x)} and {say_number(y)} each have 1 digit after the point. So the answer needs 2."
        )
        return Problem(
            "decimals",
            level,
            f"What is {say_number(x)} times {say_number(y)}?",
            value,
            (
                Step(
                    f"Let's forget the decimal points for a moment. What is {say_number(whole_x)} times "
                    f"{say_number(whole_y)}?",
                    product,
                ),
                Step(
                    f"{digits} Put the point into {say_number(product)}: what number do you get?",
                    value,
                ),
            ),
            f"{say_number(whole_x)} times {say_number(whole_y)} is {say_number(product)}. The answer needs {places} "
            f"digit{'s' if places > 1 else ''} after the point, so it is {say_number(value)}.",
        )
    x = tenths(11, 99) if level == 1 else Fraction(rng.randint(101, 999), 100)
    y = tenths(11, 99) if level == 1 else tenths(11, 59)
    op = rng.choice(("plus", "minus"))
    if op == "minus" and y > x:
        x, y = y, x
    return decimal_problem(level, x, y, op)


def decimal_problem(level: int, x: Fraction, y: Fraction, op: str) -> Problem:
    """``x`` plus or minus ``y`` (at most two decimal places), worked out as cents."""
    value = x + y if op == "plus" else x - y
    cx, cy, cents = x * 100, y * 100, value * 100
    return Problem(
        "decimals",
        level,
        f"What is {say_number(x)} {op} {say_number(y)}?",
        value,
        (
            Step(
                f"Let's think of it like money. {say_number(x)} dollars is {cx} cents, and {say_number(y)} dollars "
                f"is {cy} cents. What is {cx} {op} {cy}?",
                cents,
            ),
        ),
        f"Think of it like money: {cx} cents {op} {cy} cents is {cents} cents. "
        f"That is {say_number(value)} dollars, so the answer is {say_number(value)}.",
    )


def _percent_steps(p: int, base: int) -> tuple[tuple[Step, ...], str]:
    """Build the helper questions for p percent of base, starting from 50, 25, or 10 percent."""
    value = Fraction(p * base, 100)
    ten = Fraction(base, 10)
    find_ten = Step(f"Let's start with 10 percent. That means divide by 10. What is {base} divided by 10?", ten)
    v, t = say_number(value), say_number(ten)
    if p == 50:
        return (
            Step(f"50 percent means half. What is half of {base}?", value),
        ), f"50 percent means half: half of {base} is {v}."
    if p == 25:
        half = say_number(Fraction(base, 2))
        return (
            (Step(f"25 percent means one quarter. Half of {base} is {half}. What is half of that?", value),),
            f"25 percent is one quarter. Half of {base} is {half}, and half of that is {v}.",
        )
    if p == 75:
        quarter = say_number(Fraction(base, 4))
        return (
            (
                Step(
                    f"75 percent is three quarters. One quarter of {base} is {quarter}. What is 3 times {quarter}?",
                    value,
                ),
            ),
            f"75 percent is three quarters. One quarter of {base} is {quarter}, and 3 of those make {v}.",
        )
    if p == 10:
        return (find_ten,), f"10 percent means divide by 10, and {base} divided by 10 is {v}."
    if p == 5:
        return (
            (find_ten, Step(f"5 percent is half of 10 percent. What is half of {t}?", value)),
            f"10 percent of {base} is {t}. 5 percent is half of that, which is {v}.",
        )
    tens, rest = divmod(p, 10)
    if rest == 0:
        return (
            (find_ten, Step(f"{p} percent is {tens} times as much. What is {tens} times {t}?", value)),
            f"10 percent of {base} is {t}. {p} percent is {tens} times that, which is {v}.",
        )
    steps = [find_ten]
    tens_part = tens * ten
    if tens > 1:
        steps.append(Step(f"{tens * 10} percent is {tens} times that. What is {tens} times {t}?", tens_part))
    if rest == 5:
        rest_part = ten / 2
        steps.append(Step(f"5 percent is half of 10 percent. What is half of {t}?", rest_part))
    else:
        one = ten / 10
        rest_part = rest * one
        steps.append(
            Step(f"1 percent is {t} divided by 10, which is {say_number(one)}. What is {rest} times that?", rest_part)
        )
    steps.append(Step(f"Now add them up. What is {say_number(tens_part)} plus {say_number(rest_part)}?", value))
    return (
        tuple(steps),
        f"{tens * 10} percent of {base} is {say_number(tens_part)}, and {rest} percent is {say_number(rest_part)}. "
        f"Together, {p} percent is {v}.",
    )


def percent_numbers(level: int, rng: random.Random) -> tuple[int, int]:
    """Pick the percent and the whole of a percent problem at ``level``; the answer is a whole number."""
    p = rng.choice({1: (10, 25, 50), 2: (5, 20, 30, 40, 60, 75)}.get(level, (12, 15, 35, 45, 65, 85)))
    step = 100 // math.gcd(p, 100)
    return p, step * rng.randint(2, max(3, 400 // step))


def _percent(level: int, rng: random.Random) -> Problem:
    return percent_problem(level, *percent_numbers(level, rng))


def percent_problem(level: int, p: int, base: int) -> Problem:
    """``p`` percent of ``base``, with helper steps that start from 10, 25, or 50 percent."""
    steps, explanation = _percent_steps(p, base)
    return Problem("percent", level, f"What is {p} percent of {base}?", Fraction(p * base, 100), steps, explanation)


def _integers(level: int, rng: random.Random) -> Problem:
    a = rng.choice([n for n in range(-20, 21) if n])
    if level == 1:
        b = rng.randint(2, 20) if a < 0 else -rng.randint(2, 20)
        value = a + b
        way = "right" if b > 0 else "left"
        walk = f"Picture a number line. Start at {_signed(a)} and move {abs(b)} steps to the {way}."
        if value * a < 0 or value == 0:  # the walk reaches zero
            steps: tuple[Step, ...] = (Step(f"{walk} How many steps does it take to reach zero?", Fraction(abs(a))),)
            if value:
                steps += (
                    Step(
                        f"You have {abs(b) - abs(a)} steps left to go past zero. Where do you land?", Fraction(value)
                    ),
                )
        else:
            steps = (Step(f"{walk} Where do you land?", Fraction(value)),)
        return Problem(
            "integers",
            level,
            f"What is {_signed(a)} plus {_signed(b)}?",
            Fraction(value),
            steps,
            f"Start at {_signed(a)} on the number line and move {abs(b)} steps to the {way}. "
            f"You land on {_signed(value)}.",
        )
    if level == 2:
        b = -rng.randint(2, 20)
        value = a - b
        return Problem(
            "integers",
            level,
            f"What is {_signed(a)} minus {_signed(b)}?",
            Fraction(value),
            (
                Step(
                    f"Here's a trick: taking away a negative is the same as adding. So {_signed(a)} minus "
                    f"{_signed(b)} is the same as {_signed(a)} plus {-b}. What is {_signed(a)} plus {-b}?",
                    Fraction(value),
                ),
            ),
            f"Taking away a negative is the same as adding. So {_signed(a)} minus {_signed(b)} is "
            f"{_signed(a)} plus {-b}, which is {_signed(value)}.",
        )
    a, b = rng.choice([-1, 1]) * rng.randint(2, 12), -rng.randint(2, 12)
    value = a * b
    sign_rule = "Two negatives make a positive" if value > 0 else "One negative makes the answer negative"
    return Problem(
        "integers",
        level,
        f"What is {_signed(a)} times {_signed(b)}?",
        Fraction(value),
        (
            Step(f"First, forget the minus signs. What is {abs(a)} times {abs(b)}?", Fraction(abs(value))),
            Step(f"{sign_rule}. So what is {_signed(a)} times {_signed(b)}?", Fraction(value)),
        ),
        f"{abs(a)} times {abs(b)} is {abs(value)}. {sign_rule}, so the answer is {_signed(value)}.",
    )


def _order_of_operations(level: int, rng: random.Random) -> Problem:
    a, b, c = rng.randint(2, 12), rng.randint(2, 9), rng.randint(2, 9)
    if level == 1:
        value = a + b * c
        return Problem(
            "order_of_operations",
            level,
            f"What is {a} plus {b} times {c}?",
            Fraction(value),
            (
                Step(f"Times comes before plus. What is {b} times {c}?", Fraction(b * c)),
                Step(f"Now add {a}. What is {a} plus {b * c}?", Fraction(value)),
            ),
            f"Times comes first: {b} times {c} is {b * c}. Then {a} plus {b * c} is {value}.",
        )
    if level == 2:
        d = rng.randint(1, (a + b) * c - 1)
        value = (a + b) * c - d
        return Problem(
            "order_of_operations",
            level,
            f"What is {a} plus {b}, in parentheses, times {c}, minus {d}?",
            Fraction(value),
            (
                Step(f"Parentheses come first. What is {a} plus {b}?", Fraction(a + b)),
                Step(f"Now times {c}. What is {a + b} times {c}?", Fraction((a + b) * c)),
                Step(f"Last, take away {d}. What is {(a + b) * c} minus {d}?", Fraction(value)),
            ),
            f"Parentheses first: {a} plus {b} is {a + b}. Times {c} is {(a + b) * c}. Minus {d} is {value}.",
        )
    a = rng.randint(3, 12)
    b = rng.randint(3, 9)
    e = rng.randint(2, 9)
    f = e * rng.randint(2, 9)
    value = a * b - f // e
    return Problem(
        "order_of_operations",
        level,
        f"What is {a} times {b} minus {f} divided by {e}?",
        Fraction(value),
        (
            Step(f"Times and divide come before minus. What is {a} times {b}?", Fraction(a * b)),
            Step(f"And what is {f} divided by {e}?", Fraction(f // e)),
            Step(f"Last step: what is {a * b} minus {f // e}?", Fraction(value)),
        ),
        f"Times and divide come first. {a} times {b} is {a * b}, and {f} divided by {e} is {f // e}. "
        f"Then {a * b} minus {f // e} is {_signed(value)}.",
    )


_MYSTERY = "Think of x as a secret number."


def _equations(level: int, rng: random.Random) -> Problem:
    x = rng.randint(2, 15)
    if level == 1:
        a = rng.randint(2, 30)
        if rng.random() < 0.5:
            return Problem(
                "equations",
                level,
                f"If x plus {a} equals {x + a}, what is x?",
                Fraction(x),
                (
                    Step(
                        f"{_MYSTERY} Something plus {a} makes {x + a}. To find it, take {a} away from {x + a}. "
                        f"What is {x + a} minus {a}?",
                        Fraction(x),
                    ),
                ),
                f"Something plus {a} makes {x + a}, so x is {x + a} minus {a}, which is {x}.",
            )
        x += a
        return Problem(
            "equations",
            level,
            f"If x minus {a} equals {x - a}, what is x?",
            Fraction(x),
            (
                Step(
                    f"{_MYSTERY} Something minus {a} leaves {x - a}. To find it, put the {a} back. "
                    f"What is {x - a} plus {a}?",
                    Fraction(x),
                ),
            ),
            f"Something minus {a} leaves {x - a}, so x is {x - a} plus {a}, which is {x}.",
        )
    a = rng.randint(2, 12)
    if level == 2:
        return Problem(
            "equations",
            level,
            f"If {a} times x equals {a * x}, what is x?",
            Fraction(x),
            (Step(f"{_MYSTERY} {a} times something makes {a * x}. What is {a * x} divided by {a}?", Fraction(x)),),
            f"{a} times something makes {a * x}, so x is {a * x} divided by {a}, which is {x}.",
        )
    b = rng.randint(1, 20)
    return Problem(
        "equations",
        level,
        f"If {a} times x plus {b} equals {a * x + b}, what is x?",
        Fraction(x),
        (
            Step(f"{_MYSTERY} First, take away the {b}. What is {a * x + b} minus {b}?", Fraction(a * x)),
            Step(f"So {a} times x makes {a * x}. What is {a * x} divided by {a}?", Fraction(x)),
        ),
        f"First take away {b}: {a * x + b} minus {b} is {a * x}. Then {a} times x makes {a * x}. "
        f"So x is {a * x} divided by {a}, which is {x}.",
    )


@dataclass(frozen=True)
class Skill:
    """A practice topic and its Common Core standards."""

    name: str
    title: str
    standards: str
    generate: Generator


SKILLS: dict[str, Skill] = {
    s.name: s
    for s in (
        Skill("multiply", "multiplication", "5.NBT.5", _multiply),
        Skill("divide", "division", "6.NS.2", _divide),
        Skill("fractions", "fractions", "5.NF.1, 5.NF.4", _fractions),
        Skill("decimals", "decimals", "5.NBT.7, 6.NS.3", _decimals),
        Skill("percent", "percentages", "6.RP.3c", _percent),
        Skill("integers", "negative numbers", "7.NS.1, 7.NS.2", _integers),
        Skill("order_of_operations", "order of operations", "5.OA.1", _order_of_operations),
        Skill("equations", "equations", "6.EE.7, 7.EE.4a", _equations),
    )
}
GAME_LEVELS = (RIDDLES, CLOSEST_GUESS)  # games with a level of their own; the others use the topics' levels


# ---------------------------------------------------------------------------
# Progress per child


@dataclass
class SkillProgress:
    """Level and recent results for one skill."""

    level: int = MIN_LEVEL
    right_in_a_row: int = 0
    missed_in_a_row: int = 0
    problems: int = 0
    first_try_correct: int = 0


@dataclass
class Learner:
    """Math progress of one child, saved under ``people/<speaker_id>/``."""

    speaker_id: str
    skills: dict[str, SkillProgress] = field(default_factory=dict)
    current_skill: str = next(iter(SKILLS))
    problems_in_skill: int = 0
    theme: str = ""  # what the child likes, for stories and guessing games, such as "dogs"
    games_explained: list[str] = field(default_factory=list)  # games whose rules Reachy has told this child

    def skill(self, name: str) -> SkillProgress:
        """Progress for ``name``, created at level 1 on first use."""
        return self.skills.setdefault(name, SkillProgress())

    def to_json(self) -> dict[str, Any]:
        """Serialize for math_progress.json."""
        return {
            "speaker_id": self.speaker_id,
            "current_skill": self.current_skill,
            "problems_in_skill": self.problems_in_skill,
            "theme": self.theme,
            "games_explained": self.games_explained,
            "skills": {name: asdict(p) for name, p in self.skills.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Learner:
        """Load from math_progress.json, ignoring unknown skills and fields."""
        learner = cls(str(data.get("speaker_id", UNKNOWN)))
        if data.get("current_skill") in SKILLS:
            learner.current_skill = str(data["current_skill"])
            learner.problems_in_skill = int(data.get("problems_in_skill", 0))
        learner.theme = str(data.get("theme") or "")
        learner.games_explained = [g for g in data.get("games_explained") or [] if g in GAMES]
        known = set(SkillProgress.__dataclass_fields__)
        for name, values in dict(data.get("skills", {})).items():
            if (name in SKILLS or name in GAME_LEVELS) and isinstance(values, dict):
                learner.skills[name] = SkillProgress(**{k: int(v) for k, v in values.items() if k in known})
        return learner


def _pick_skill(learner: Learner, topic: str | None) -> None:
    """Switch quick math to ``topic`` if one is asked for, or to the next topic after a few problems."""
    if topic in SKILLS and topic != learner.current_skill:
        learner.current_skill, learner.problems_in_skill = str(topic), 0
    elif topic not in SKILLS and learner.problems_in_skill >= PROBLEMS_PER_SKILL:
        names = list(SKILLS)
        learner.current_skill = names[(names.index(learner.current_skill) + 1) % len(names)]
        learner.problems_in_skill = 0


def record_result(progress: SkillProgress, outcome: str) -> int:
    """Apply the level rule to one finished problem; return the level change (-1, 0, or 1).

    ``outcome`` is ``first_try`` (right on the first try), ``second_try`` (right on the second
    try, before any helper step), ``with_help`` (solved through the helper steps, every one
    answered right), or ``missed`` (Reachy had to give away an answer).
    """
    progress.problems += 1
    if outcome == "first_try":
        progress.first_try_correct += 1
        progress.right_in_a_row += 1
        progress.missed_in_a_row = 0
    elif outcome == "missed":
        progress.missed_in_a_row += 1
        progress.right_in_a_row = 0
    else:
        progress.right_in_a_row = progress.missed_in_a_row = 0
    if progress.right_in_a_row >= LEVEL_UP_AFTER:
        progress.right_in_a_row = 0
        if progress.level < MAX_LEVEL:
            progress.level += 1
            return 1
    if progress.missed_in_a_row >= LEVEL_DOWN_AFTER:
        progress.missed_in_a_row = 0
        if progress.level > MIN_LEVEL:
            progress.level -= 1
            return -1
    return 0


# ---------------------------------------------------------------------------
# The coach: one open problem at a time, shared by everyone at the robot


@dataclass
class OpenProblem:
    """The problem Reachy has asked and is waiting on."""

    problem_id: str
    problem: Problem
    asked_to: str
    asked_mono: float
    attempts: int = 0
    step: int | None = None  # index of the helper step being asked; None while on the problem itself
    gave_away: bool = False  # Reachy told the child a helper answer


class MathCoach:
    """Hands out problems, checks answers, and keeps each child's progress. Thread-safe."""

    def __init__(self, rng: random.Random | None = None) -> None:
        """Start with no open problem and no practice under way."""
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._learners: dict[str, Learner] = {}
        self._open: OpenProblem | None = None
        self._count = 0
        self._last_activity_mono: float | None = None
        self._last_offer_mono: float | None = None
        self._session_results: dict[str, list[str]] = {}
        self._rounds = 0  # rounds started in this app run
        self._round_count = 0  # problems opened in the current round
        self._round_first_try = 0  # of those, answered right on the first try
        self._turns_since_math = 0  # things people said since the last math tool call
        self._game: str | None = None  # the game of the round under way; None between rounds
        self._theme = ""  # what the story or guessing game of this round is about
        self._round_start = 0  # random number picked at the start of a round, so rounds differ
        self._explained_this_round = False  # Reachy told the rules of this round's game before its first problem
        self._offer_index = self._rng.randrange(len(GAMES))
        self._offered = self._next_offer()  # the two games Reachy lets the child pick from next

    # -- who is answering

    @staticmethod
    def _speaker() -> str:
        return voice_id.current_speaker() or UNKNOWN

    @staticmethod
    def _progress_path(speaker_id: str) -> Path | None:
        ident = voice_id.identifier()
        if ident is None or speaker_id == UNKNOWN:
            return None  # unidentified children practice without saved progress
        return person_dir(ident.data_dir, speaker_id) / PROGRESS_FILENAME

    def _learner(self, speaker_id: str) -> Learner:
        learner = self._learners.get(speaker_id)
        if learner is None:
            learner = Learner(speaker_id)
            path = self._progress_path(speaker_id)
            if path is not None and path.exists():
                try:
                    learner = Learner.from_json(json.loads(path.read_text(encoding="utf-8")))
                    learner.speaker_id = speaker_id
                except (OSError, ValueError, TypeError) as e:
                    logger.warning("Could not read %s, starting fresh: %s", path, e)
            self._learners[speaker_id] = learner
        return learner

    def _save(self, learner: Learner) -> None:
        path = self._progress_path(learner.speaker_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(learner.to_json(), indent=1), encoding="utf-8")
        tmp.replace(path)

    # -- practice flow

    def next_problem(
        self, topic: str | None = None, game: str | None = None, theme: str | None = None
    ) -> dict[str, Any]:
        """Open the next problem for whoever is speaking now.

        A new round starts when none is under way, the last one is over, or the child picks
        another game. If the child has not played that game before, Reachy first gets its
        rules instead of a problem, and the next call opens the first problem. ``topic`` means
        quick math on that topic; ``theme`` is saved as what the child likes and is used by
        stories and guessing games from now on.
        """
        from talk_with_reachy_math import math_games

        with self._lock:
            if topic in SKILLS:
                game = QUICK_MATH
            learner = self._learner(self._speaker())
            if theme in math_games.THEMES and theme != learner.theme:
                learner.theme = self._theme = str(theme)
                self._save(learner)
            new_game = game if game in GAMES else None
            if (
                self._game is None
                or self._round_count >= ROUND_SIZE
                or not self.practice_active()
                or (new_game is not None and new_game != self._game)
            ):
                self._rounds += 1
                self._round_count = self._round_first_try = 0
                self._game = new_game or self._game or self._offered[0]  # after a long pause, the same game again
                self._round_start = self._rng.randrange(1000)
                self._explained_this_round = False
                themes = list(math_games.THEMES)
                self._theme = learner.theme if learner.theme in themes else self._rng.choice(themes)
                if self._game not in learner.games_explained:
                    return self._explain(learner, topic)
            return self._open_next(topic)

    def _explain(self, learner: Learner, topic: str | None) -> dict[str, Any]:
        """Give Reachy the rules of the round's game, before its first problem. Caller holds the lock."""
        from talk_with_reachy_math import math_games

        game = self._game or QUICK_MATH
        if game == QUICK_MATH:
            _pick_skill(learner, topic)  # so the first problem, asked by the next call, has the topic named here
        if self._open is not None:  # the child switched games in the middle of a problem
            study_log.record_event(
                "math_problem_skipped", problem_id=self._open.problem_id, attempts=self._open.attempts
            )
            self._open = None
        learner.games_explained.append(game)
        self._save(learner)
        self._explained_this_round = True
        self._last_activity_mono = time.monotonic()
        self._turns_since_math = 0
        study_log.record_event("math_game_explained", speaker_id=learner.speaker_id, game=game, round=self._rounds)
        return {
            "game": math_games.TITLES[game],
            "how_to_play": math_games.HOW_TO_PLAY[game],
            "instructions": f"{self._round_start_note(game, learner)}; say so in a few fun words. Then read the "
            "'how_to_play' text exactly. Then ask if they are ready, and wait. When they say they are ready, call "
            "next_math_problem to get the first problem. If they ask how to play, read 'how_to_play' again.",
        }

    def _round_start_note(self, game: str, learner: Learner) -> str:
        """Tell Reachy what kind of round starts now. Caller holds the lock."""
        title = SKILLS[learner.current_skill].title
        return {
            QUICK_MATH: f"This starts a round of {ROUND_SIZE} {title} problems",
            STORY: f"This starts a story adventure in {ROUND_SIZE} parts",
            FIX_MY_MISTAKE: f"This starts a round of {ROUND_SIZE} of your mistakes, and you need their help",
            RIDDLES: f"This starts a round of {ROUND_SIZE} number riddles",
            CLOSEST_GUESS: f"This starts a closest guess game of {ROUND_SIZE} questions, and the closer guess wins",
        }[game]

    def _open_next(self, topic: str | None) -> dict[str, Any]:
        """Pick, open, and log a problem of the round's game; return what Reachy needs to ask it. Caller holds the lock."""
        from talk_with_reachy_math import math_games

        speaker_id = self._speaker()
        learner = self._learner(speaker_id)
        game = self._game or QUICK_MATH
        if game == QUICK_MATH:
            _pick_skill(learner, topic)
            skill = SKILLS[learner.current_skill]
            problem = skill.generate(learner.skill(skill.name).level, self._rng)
            learner.problems_in_skill += 1
        else:
            turn = math_games.Turn(
                self._round_count + 1,
                lambda name: learner.skill(name).level,
                math_games.THEMES[self._theme],
                self._round_start,
                self._rng,
            )
            problem = math_games.MAKERS[game](turn)
        if self._open is not None:
            study_log.record_event(
                "math_problem_skipped", problem_id=self._open.problem_id, attempts=self._open.attempts
            )
        self._count += 1
        self._round_count += 1
        self._turns_since_math = 0
        problem_id = f"M{self._count:03d}"
        now = time.monotonic()
        self._open = OpenProblem(problem_id, problem, speaker_id, now)
        self._last_activity_mono = now
        self._save(learner)
        topic_skill = SKILLS.get(problem.skill)
        study_log.record_event(
            "math_problem",
            now,
            problem_id=problem_id,
            asked_to=speaker_id,
            game=problem.game,
            theme=problem.theme or None,
            skill=problem.skill,
            level=problem.level,
            standards=topic_skill.standards if topic_skill else math_games.STANDARDS.get(problem.skill, ""),
            text=problem.text,
            answer=problem.answer_text,
            reachy_answer=None if problem.reachy_answer is None else say_number(problem.reachy_answer),
            source=problem.source,
            round=self._rounds,
            position=self._round_count,
        )
        instructions = (
            "Read the 'say' text exactly as written, then wait for the answer. "
            "Never say or hint at the answer before the child has tried."
        )
        game_note = {
            STORY: "Read it like a storyteller.",
            FIX_MY_MISTAKE: "Read it as your own work, in a playful way.",
            RIDDLES: "Read the clues slowly.",
            CLOSEST_GUESS: "Do not say your own guess or the real answer yet; check_math_answer gives them to you.",
        }.get(game)
        if game_note:
            instructions += f" {game_note}"
        result: dict[str, Any] = {
            "problem_id": problem_id,
            "say": problem.text,
            "game": math_games.TITLES[game],
            "topic": topic_skill.title if topic_skill else math_games.TITLES[game],
            "level": problem.level,
            "round_position": f"{self._round_count} of {ROUND_SIZE}",
        }
        if self._round_count == 1 and self._explained_this_round and game == QUICK_MATH and topic in SKILLS:
            instructions = f"This round is about {SKILLS[learner.current_skill].title} now; say so. {instructions}"
        if self._round_count == 1 and not self._explained_this_round:
            # The child has played this game before: one line about it instead of the rules.
            result["reminder"] = math_games.REMINDERS[game]
            result["how_to_play"] = math_games.HOW_TO_PLAY[game]
            instructions = (
                f"{self._round_start_note(game, learner)}; say so in a few fun words, then say the 'reminder' text. "
                f"{instructions} If they ask how to play, read 'how_to_play' exactly."
            )
        result["instructions"] = instructions
        return result

    def check_answer(self, child_answer: str) -> dict[str, Any]:
        """Check what the child said against the open problem or helper step, and say what Reachy does next."""
        from talk_with_reachy_math import math_games

        with self._lock:
            open_problem = self._open
            if open_problem is None:
                return {"error": "No problem is open. Call next_math_problem first."}
            now = time.monotonic()
            self._last_activity_mono = now
            self._turns_since_math = 0
            speaker_id = self._speaker()
            problem = open_problem.problem
            heard = parse_answer(child_answer)
            fields: dict[str, Any] = {
                "problem_id": open_problem.problem_id,
                "answered_by": speaker_id,
                "asked_to": open_problem.asked_to,
                "heard": child_answer,
                "parsed": None if heard is None else say_number(heard),
                "step": None if open_problem.step is None else open_problem.step + 1,
                "seconds_since_asked": round(now - open_problem.asked_mono, 1),
            }
            if problem.game == CLOSEST_GUESS and heard is not None:
                open_problem.attempts += 1
                fields["attempt"] = open_problem.attempts
                return self._finish_guess(open_problem, speaker_id, heard, now, fields)
            asks_for_help = heard is None and _ASKS_FOR_HELP.search(child_answer) is not None
            feels_stuck = heard is None and _FEELS_STUCK.search(child_answer) is not None
            if heard is None and (problem.game == CLOSEST_GUESS or not (asks_for_help or feels_stuck)):
                study_log.record_event("math_answer", now, **fields, attempt=None, correct=None)
                ask_again = {
                    CLOSEST_GUESS: "You did not hear a number. Kindly ask for their best guess as a number; any guess "
                    "is fine.",
                    FIX_MY_MISTAKE: "You did not hear a number. If they said your answer is not right, agree happily "
                    "and ask them what the real answer is. Otherwise kindly ask for their answer as a number, or to "
                    "say 'help' if they are stuck.",
                }
                return {
                    "heard_a_number": False,
                    "instructions": ask_again.get(
                        problem.game,
                        "You did not hear a number. Kindly ask them to say their answer as a number, "
                        "or to say 'help' if they are stuck.",
                    ),
                }
            open_problem.attempts += 1
            fields["attempt"] = open_problem.attempts
            if heard is not None and answer_matches(heard, problem.answer):
                if open_problem.step is None:
                    outcome = "first_try" if open_problem.attempts == 1 else "second_try"
                else:
                    outcome = "missed" if open_problem.gave_away else "with_help"
                return self._finish(open_problem, speaker_id, outcome, True, now, fields)
            if open_problem.step is None:
                close = (
                    heard is not None
                    and problem.game in (QUICK_MATH, STORY)
                    and problem.answer != 0
                    and abs(heard - problem.answer) <= abs(problem.answer) * CLOSE_ENOUGH
                )
                fields["close"] = close
                miss = (
                    math_games.riddle_miss(problem, heard) if problem.game == RIDDLES and heard is not None else None
                )
                if miss:
                    fields["clue_missed"] = miss
                if open_problem.attempts == 1 and not asks_for_help:
                    return self._try_again(open_problem, heard, close, miss, now, fields)
                if not problem.steps:
                    return self._finish(open_problem, speaker_id, "missed", False, now, fields)
                study_log.record_event("math_answer", now, **fields, correct=False, reply="helper_question")
                open_problem.step = 0
                if problem.game == FIX_MY_MISTAKE and heard is not None and heard == problem.reachy_answer:
                    opener = "Say happily that you got that answer too, so let's check it together."
                elif close:
                    opener = "Their answer is really close: tell them it was a great estimate."
                elif heard is None:
                    opener = "Tell them that's okay, it's a tricky one."
                else:
                    opener = "Say 'Not quite yet' or 'Good try' warmly; never say 'wrong'."
                result: dict[str, Any] = {"correct": False, "close": close}
                if miss:
                    result["clue_missed"] = miss
                    opener += f' Then say: "{miss}"'
                result["helper_question"] = problem.steps[0].ask
                result["instructions"] = (
                    f"{opener} Do not say the answer. Say you will work it out together in small steps, then ask the "
                    "helper question exactly as written. Wait for their answer and pass it to check_math_answer."
                )
                return result
            step = problem.steps[open_problem.step]
            step_right = heard is not None and step.matches(heard)
            open_problem.gave_away = open_problem.gave_away or not step_right
            next_index = open_problem.step + 1
            if next_index >= len(problem.steps):
                outcome = "missed" if open_problem.gave_away else "with_help"
                return self._finish(open_problem, speaker_id, outcome, step_right, now, fields)
            study_log.record_event("math_answer", now, **fields, correct=step_right)
            open_problem.step = next_index
            follow = "Then ask the next helper question exactly as written, and pass the answer to check_math_answer."
            if step_right:
                return {
                    "correct": True,
                    "helper_question": problem.steps[next_index].ask,
                    "instructions": f"Say 'Yes!' or 'Nice!' in a few words. {follow}",
                }
            example = "That's okay!" if heard is None else "Almost!"
            return {
                "correct": False,
                "helper_answer": step.answer_text,
                "helper_question": problem.steps[next_index].ask,
                "instructions": f"Kindly tell them this step's answer, for example '{example} It's {step.answer_text}.' "
                f"{follow}",
            }

    @staticmethod
    def _try_again(
        open_problem: OpenProblem,
        heard: Fraction | None,
        close: bool,
        miss: str | None,
        now: float,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """After a first answer that is not right, give the child time to think again, without a hint yet.

        The helper questions start after a second answer that is not right, or when the child asks for help.
        Caller holds the lock.
        """
        problem = open_problem.problem
        study_log.record_event("math_answer", now, **fields, correct=False, reply="try_again")
        if problem.game == FIX_MY_MISTAKE and heard is not None and heard == problem.reachy_answer:
            opener = (
                "Say happily that you got that answer too, but you think one of your steps has a mistake. Ask them "
                "to check your work again and find the real answer."
            )
        elif close:
            opener = (
                "Their answer is really close: tell them it was a great estimate, and ask them to check it once more."
            )
        elif heard is None:
            opener = (
                "Tell them that's okay, it's a tricky one. Tell them to take their time and think, and that they can "
                "say 'help' for a hint."
            )
        elif miss:
            opener = f'Say "Not quite yet", then say: "{miss}" Ask them to try another number that fits every clue.'
        else:
            opener = (
                "Say 'Not quite yet' or 'Good try' warmly; never say 'wrong'. Ask them to take their time, think "
                "again, and try once more."
            )
        result: dict[str, Any] = {"correct": False, "close": close, "try_again": True, "problem": problem.text}
        if miss:
            result["clue_missed"] = miss
        result["instructions"] = (
            f"{opener} Do not give a hint and do not say the answer. If they ask to hear the problem again, read "
            "'problem' exactly. Then wait for their answer and pass it to check_math_answer."
        )
        return result

    def _finish_guess(
        self, open_problem: OpenProblem, speaker_id: str, guess: Fraction, now: float, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Close a closest guess problem: whose guess is closer, the child's or Reachy's? Caller holds the lock."""
        problem = open_problem.problem
        reachy = problem.reachy_answer if problem.reachy_answer is not None else problem.answer
        child_off, reachy_off = abs(guess - problem.answer), abs(reachy - problem.answer)
        winner = "child" if child_off < reachy_off else "reachy" if reachy_off < child_off else "tie"
        close = child_off <= abs(problem.answer) * CLOSE_ENOUGH
        fields.update(reachy_guess=say_number(reachy), winner=winner, close=close)
        cheer = {
            "child": "Cheer: their guess is closer, so they win this one!",
            "reachy": "Say your guess was closer this time, and theirs was a good try.",
            "tie": "Say it's a tie!",
        }[winner]
        wrap_up = (
            f"Now say your own guess: {say_number(reachy)}. Then say the real answer: {problem.answer_text}. {cheer} "
            "Then share the trick in the explanation in one or two short sentences."
        )
        result = self._finish(
            open_problem, speaker_id, "first_try" if close else "with_help", close, now, fields, wrap_up
        )
        result.update(
            your_guess=say_number(guess),
            reachy_guess=say_number(reachy),
            winner=winner,
            explanation=problem.explanation,
        )
        return result

    def _finish(
        self,
        open_problem: OpenProblem,
        speaker_id: str,
        outcome: str,
        correct: bool,
        now: float,
        fields: dict[str, Any],
        wrap_up: str | None = None,
    ) -> dict[str, Any]:
        """Close the problem, update the child's level, and tell Reachy what to say next. Caller holds the lock."""
        from talk_with_reachy_math import math_games

        problem = open_problem.problem
        learner = self._learner(speaker_id)
        progress = learner.skill(problem.skill)
        old_level = progress.level
        change = record_result(progress, outcome)
        self._save(learner)
        self._open = None
        self._session_results.setdefault(speaker_id, []).append(outcome)
        study_log.record_event("math_answer", now, **fields, correct=correct, outcome=outcome)
        if change:
            study_log.record_event(
                "math_level_change",
                now,
                speaker_id=speaker_id,
                skill=problem.skill,
                old_level=old_level,
                new_level=progress.level,
            )
        result: dict[str, Any] = {"correct": correct, "answer": problem.answer_text}
        if outcome == "first_try":
            self._round_first_try += 1
        fixed = problem.game == FIX_MY_MISTAKE
        on_their_own = outcome in ("first_try", "second_try")  # right without helper questions
        if wrap_up is None and on_their_own:
            wrap_up = (
                "Thank them for fixing your mistake, in a few happy words. Then ask them: 'What did I do wrong?' and "
                "stop to let them answer. Their answer to that is not a math answer, so do not pass it to "
                "check_math_answer. When they have answered, thank them."
                if fixed
                else "Praise them out loud in a few specific words."
                if outcome == "first_try"
                else "Praise them out loud for thinking again and getting it, in a few specific words."
            )
        elif wrap_up is None and correct:
            result["explanation"] = problem.explanation
            wrap_up = (
                f"Cheer out loud: they worked it out step by step! Say the whole answer, {problem.answer_text}, "
                "in one short sentence."
                + (" Then say what your mistake was, in one short sentence from the explanation." if fixed else "")
            )
        elif wrap_up is None:
            result["explanation"] = problem.explanation
            wrap_up = (
                f"Kindly tell them the answer is {problem.answer_text}, then explain it with the explanation in two "
                "or three short, simple sentences. Praise their effort; tricky ones help their brain grow."
            )
        then = "After you thank them," if fixed and on_their_own else "Then"
        if self._round_count < ROUND_SIZE:
            # The next problem waits until the child says they are ready, so they have time to take in the answer.
            result["round_position"] = f"{self._round_count} of {ROUND_SIZE} done"
            what = "the next part of the story" if problem.game == STORY else "the next one"
            go_on = (
                f"{then} ask if they are ready for {what}, in a few words, and wait. When they say they are ready, "
                "call next_math_problem. If they want another game instead, call next_math_problem with that game."
            )
        else:
            done, first_try = self._round_count, self._round_first_try
            result["round_finished"] = {"problems": done, "first_try_correct": first_try}
            how = (
                f"{first_try} of their guesses were close"
                if problem.game == CLOSEST_GUESS
                else f"{first_try} of them right on the first try"
            )
            go_on = f"{then} cheer that they finished all {done}: {how}."
            if problem.game == STORY:
                theme = math_games.THEMES.get(problem.theme)
                ending = theme.end if theme else "The end!"
                result["story_end"] = ending
                go_on = f'{then} read the end of the story: "{ending}" Then cheer that they finished all {done} parts.'
            self._game = None
            self._offered = self._next_offer()
            go_on += (
                f" Then let them pick the next game: {self._choice()}, or a short break. When they pick a game, call "
                "next_math_problem with it."
            )
        result["instructions"] = f"{wrap_up} {go_on}"
        if change > 0:
            name = SKILLS[problem.skill].title if problem.skill in SKILLS else math_games.TITLES[problem.skill]
            result["level_change"] = f"They move up to level {progress.level} in {name}."
        elif change < 0:
            name = SKILLS[problem.skill].title if problem.skill in SKILLS else math_games.TITLES[problem.skill]
            result["level_change"] = f"The next {name} problems will be a bit easier."
        return result

    # -- choosing games

    def _next_offer(self) -> tuple[str, str]:
        """Pick the next two games to offer; over a few rounds, every game comes up."""
        i = self._offer_index
        self._offer_index += 2
        return GAMES[i % len(GAMES)], GAMES[(i + 1) % len(GAMES)]

    def _choice(self) -> str:
        """Name the two offered games, as Reachy says them and as the tool names them."""
        from talk_with_reachy_math import math_games

        a, b = self._offered
        return f"{math_games.TITLES[a]} (game '{a}') or {math_games.TITLES[b]} (game '{b}')"

    def stop(self, reason: str = "") -> dict[str, Any]:
        """End the practice and report how it went for each child."""
        with self._lock:
            if self._open is not None:
                study_log.record_event(
                    "math_problem_skipped", problem_id=self._open.problem_id, attempts=self._open.attempts
                )
            self._open = None
            self._game = None
            self._last_activity_mono = None
            self._last_offer_mono = time.monotonic()  # wait a full interval before inviting again
            self._round_count = self._round_first_try = self._turns_since_math = 0
            summary = {
                speaker: {"problems": len(results), "first_try_correct": results.count("first_try")}
                for speaker, results in self._session_results.items()
            }
            self._session_results = {}
        study_log.record_event("math_practice_stopped", reason=reason, results=summary)
        return {"stopped": True, "results": summary}

    # -- offering practice

    def practice_active(self, now: float | None = None) -> bool:
        """Return whether problems are being worked on (until stopped or idle for 10 minutes)."""
        now = time.monotonic() if now is None else now
        last = self._last_activity_mono
        return last is not None and now - last < PRACTICE_IDLE_S

    def connection_opened(self, now: float | None = None) -> None:
        """Start the offer clock: the greeting at the start already starts a math game."""
        self._last_offer_mono = time.monotonic() if now is None else now

    def greeting_with_game_choice(self, greeting: str) -> str:
        """Add a choice of two games to the startup greeting, so that Reachy starts the math right away.

        Practice counts as under way from here, so if the child talks about something else,
        Reachy is told to come back to the choice.
        """
        with self._lock:
            self._last_activity_mono = time.monotonic()
            self._turns_since_math = 0
            choice = self._choice()
        return (
            f"{greeting}\nThen, in the same reply, let them pick a math game: {choice}. When they pick, call "
            "next_math_problem with that game. If they do not pick, pick one yourself and call next_math_problem."
        )

    def note_after_user_turn(self, text: str, now: float | None = None) -> str | None:
        """Count one thing a person said; return a system note when Reachy should steer back to math or offer it.

        While practice is under way, a note is returned after the 2nd and 5th thing in a row that the
        math tools did not handle, unless it contains a number (then it is probably an answer).
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            if not enabled():
                return None
            steer: str | None = None
            turns, problem_id, speaker_id = 0, None, UNKNOWN
            if self.practice_active(now):
                self._turns_since_math += 1
                turns, open_problem = self._turns_since_math, self._open
                if turns not in STEER_AFTER_TURNS or (open_problem is not None and parse_answer(text) is not None):
                    return None
                between_problems = open_problem is None and self._game is not None and self._round_count < ROUND_SIZE
                if between_problems and turns < STEER_AFTER_TURNS[-1]:
                    # Between two problems the child may still be telling what Reachy did wrong, or asking
                    # how to play, before saying they are ready; only a longer drift gets a note.
                    return None
                if open_problem is not None:
                    step = open_problem.step
                    waiting = open_problem.problem.text if step is None else open_problem.problem.steps[step].ask
                    steer = (
                        f'Math practice: the math question "{waiting}" is still waiting. Reply to what the child just '
                        "said in one short, friendly sentence, then bring them back to the question in a fun way, for "
                        "example by asking it again."
                    )
                elif self._game is not None and self._round_count < ROUND_SIZE:
                    steer = (
                        "Math practice: reply to what the child just said in one short, friendly sentence, then ask if "
                        "they are ready for the next math problem. When they say they are ready, call "
                        "next_math_problem. If they clearly said they want to stop playing, call stop_math_practice "
                        "instead."
                    )
                else:
                    steer = (
                        "Math practice: reply to what the child just said in one short, friendly sentence, then let "
                        f"them pick the next math game: {self._choice()}. When they pick, call next_math_problem with "
                        "it. If they clearly said they want to stop playing, call stop_math_practice instead."
                    )
                problem_id = None if open_problem is None else open_problem.problem_id
                speaker_id = self._speaker()
        if steer is None:
            return self.offer_note_if_due(now)
        study_log.record_event(
            "math_steer_prompted", now, speaker_id=speaker_id, problem_id=problem_id, turns_without_math=turns
        )
        return steer

    def offer_note_if_due(self, now: float | None = None) -> str | None:
        """Return a system note asking Reachy to offer practice if it is time, else None."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if not enabled() or self._last_offer_mono is None or self.practice_active(now):
                return None
            if now - self._last_offer_mono < offer_after_s():
                return None
            self._last_offer_mono = now
        speaker_id = self._speaker()
        ident = voice_id.identifier()
        name = ident.name_of(speaker_id) if ident is not None and speaker_id != UNKNOWN else ""
        study_log.record_event("math_offer_prompted", now, speaker_id=speaker_id)
        who = name or "the person you are talking with"
        with self._lock:
            choice = self._choice()
        return (
            f"Math practice: when there is a natural pause, invite {who} back to a math game in a fun way: {choice}. "
            "If they say no, let it go and keep chatting. If they pick one, call next_math_problem with it."
        )


_coach = MathCoach()


def coach() -> MathCoach:
    """Return the app's math coach."""
    return _coach


def topics() -> list[str]:
    """Topic names the next_math_problem tool accepts."""
    return list(SKILLS)
