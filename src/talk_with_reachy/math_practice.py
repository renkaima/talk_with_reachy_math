"""Spoken math practice for children aged about 10 to 13 (US grades 5 to 7).

Problems are generated, or for word problems drawn from GSM8K, and checked here in
code. The conversation model only reads a problem aloud and passes on what the child
said, so the answer Reachy confirms is always computed, never guessed by the model.

Each child has a level from 1 to 3 per skill, kept in ``people/<speaker_id>/math_progress.json``
and found through voice ID. Levels follow a fixed rule: three problems in a row answered
correctly on the first try move the child up one level; two problems in a row not solved
after the second try move them down one level. A problem solved on the second try leaves
the level alone and resets both counts.

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

from talk_with_reachy import voice_id, study_log
from talk_with_reachy.voice_files import UNKNOWN, person_dir


logger = logging.getLogger(__name__)

MATH_ENV = "TALK_WITH_REACHY_MATH"
OFFER_AFTER_ENV = "TALK_WITH_REACHY_MATH_OFFER_AFTER_S"
DEFAULT_OFFER_AFTER_S = 120.0
REOFFER_AFTER_S = 600.0
PRACTICE_IDLE_S = 600.0  # practice counts as over after this long without a math tool call
PROGRESS_FILENAME = "math_progress.json"
WORD_PROBLEMS_PATH = Path(__file__).parent / "math_data" / "word_problems.jsonl"

MIN_LEVEL, MAX_LEVEL = 1, 3
LEVEL_UP_AFTER = 3  # first-try correct answers in a row
LEVEL_DOWN_AFTER = 2  # problems not solved in a row
PROBLEMS_PER_SKILL = 5  # then the next problem without a topic moves on to the next skill
MAX_ATTEMPTS = 2


def enabled() -> bool:
    """Return whether math practice is on (it is unless the env var is 0)."""
    return os.getenv(MATH_ENV, "1").strip() != "0"


def offer_after_s() -> float:
    """Seconds of conversation before Reachy first offers math practice."""
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
class Problem:
    """One problem, as Reachy should read it, with everything needed to check and explain it."""

    skill: str
    level: int
    text: str
    answer: Fraction
    hint: str
    explanation: str
    source: str = "generated"

    @property
    def answer_text(self) -> str:
        """How Reachy says the answer: fractions as fractions, other answers as numbers."""
        return say_fraction(self.answer) if self.skill == "fractions" else say_number(self.answer)


Generator = Callable[[int, random.Random], Problem]


def _multiply(level: int, rng: random.Random) -> Problem:
    a = (
        rng.choice([n for n in range(101, 1000) if n % 10])
        if level == 3
        else rng.choice([n for n in range(12, 100) if n % 10])
    )
    b = rng.randint(3, 9) if level == 1 else rng.choice([n for n in range(11, 100) if n % 10])
    if level == 1:
        hint = f"Split {a} into {a // 10 * 10} and {a % 10}, multiply each by {b}, then add."
    else:
        hint = f"Multiply {a} by {b // 10 * 10} first, then {a} by {b % 10}, and add the two."
    return Problem(
        "multiply",
        level,
        f"What is {a} times {b}?",
        Fraction(a * b),
        hint,
        f"{a} times {b // 10 * 10} is {a * (b // 10 * 10)}, and {a} times {b % 10} is {a * (b % 10)}. "
        f"Together that makes {a * b}."
        if b >= 10
        else f"{a} times {b} is {a * b}.",
    )


def _divide(level: int, rng: random.Random) -> Problem:
    if level == 1:
        q, d = rng.randint(12, 99), rng.randint(3, 9)
    elif level == 2:
        q, d = rng.randint(11, 39), rng.randint(11, 25)
    else:
        q, d = rng.randint(21, 99), rng.randint(12, 49)
    n = q * d
    guess = max(10, round(q, -1))
    return Problem(
        "divide",
        level,
        f"What is {n} divided by {d}?",
        Fraction(q),
        f"Ask yourself: {d} times what makes {n}? Try {guess} first: {d} times {guess} is {d * guess}.",
        f"{n} divided by {d} is {q}, because {d} times {q} is {n}.",
    )


_NICE_DENOMINATORS = (2, 3, 4, 5, 6, 8, 10, 12)


def _fractions(level: int, rng: random.Random) -> Problem:
    if level == 1:
        d = rng.randint(5, 12)
        a = rng.randint(1, d - 2)
        b = rng.randint(1, d - 1 - a)
        x, y = Fraction(a, d), Fraction(b, d)
        return Problem(
            "fractions",
            level,
            f"What is {_proper_fraction_words(a, d)} plus {_proper_fraction_words(b, d)}?",
            x + y,
            "The bottom numbers are the same, so add the top numbers and keep the bottom.",
            f"{a} plus {b} is {a + b}, so the answer is {_proper_fraction_words(a + b, d)}"
            + (f", which is the same as {say_fraction(x + y)}." if (x + y).denominator != d else "."),
        )
    if level == 2:
        d1, d2 = rng.sample(_NICE_DENOMINATORS, 2)
        x = Fraction(rng.randint(1, d1 - 1), d1)
        y = Fraction(rng.randint(1, d2 - 1), d2)
        common = math.lcm(d1, d2)
        if rng.random() < 0.5 or x == y:
            op, value = "plus", x + y
        else:
            x, y = max(x, y), min(x, y)
            op, value = "minus", x - y
        xs, ys = (_proper_fraction_words(f.numerator * common // f.denominator, common) for f in (x, y))
        return Problem(
            "fractions",
            level,
            f"What is {say_fraction(x)} {op} {say_fraction(y)}?",
            value,
            f"Rewrite both fractions with the same bottom number. {common} works for both.",
            f"{say_fraction(x)} is {xs} and {say_fraction(y)} is {ys}, so the answer is {say_fraction(value)}.",
        )
    if rng.random() < 0.5:
        d = rng.choice(_NICE_DENOMINATORS[1:])
        x = Fraction(rng.randint(1, d - 1), d)
        whole = d * rng.randint(2, 9)
        value = x * whole
        return Problem(
            "fractions",
            level,
            f"What is {say_fraction(x)} of {whole}?",
            value,
            f"First find 1 {_DENOMINATOR_WORDS[d][0]} of {whole} by dividing by {d}.",
            f"{whole} divided by {d} is {whole // d}"
            + (f", and {x.numerator} of those make {say_number(value)}." if x.numerator > 1 else "."),
        )
    d1, d2 = rng.sample(_NICE_DENOMINATORS, 2)
    x = Fraction(rng.randint(1, d1 - 1), d1)
    y = Fraction(rng.randint(1, d2 - 1), d2)
    value = x * y
    return Problem(
        "fractions",
        level,
        f"What is {say_fraction(x)} times {say_fraction(y)}?",
        value,
        "Multiply the top numbers together and the bottom numbers together.",
        f"Top times top is {x.numerator * y.numerator}, bottom times bottom is {x.denominator * y.denominator}, "
        f"so the answer is {say_fraction(value)}.",
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
        return Problem(
            "decimals",
            level,
            f"What is {say_number(x)} times {say_number(y)}?",
            value,
            "Multiply as if there were no decimal points, then put back as many decimal places as the two "
            "numbers have together.",
            f"{say_number(x)} times {say_number(y)} is {say_number(value)}.",
        )
    x = tenths(11, 99) if level == 1 else Fraction(rng.randint(101, 999), 100)
    y = tenths(11, 99) if level == 1 else tenths(11, 59)
    op = rng.choice(("plus", "minus"))
    if op == "minus" and y > x:
        x, y = y, x
    value = x + y if op == "plus" else x - y
    return Problem(
        "decimals",
        level,
        f"What is {say_number(x)} {op} {say_number(y)}?",
        value,
        "Line up the decimal points, and fill an empty place with a zero if it helps.",
        f"{say_number(x)} {op} {say_number(y)} is {say_number(value)}.",
    )


_PERCENT_HINTS = {
    50: "50 percent is one half.",
    25: "25 percent is one quarter: divide by 4.",
    75: "75 percent is three quarters: find one quarter first, then take 3 of them.",
}


def _percent(level: int, rng: random.Random) -> Problem:
    p = rng.choice({1: (10, 25, 50), 2: (5, 20, 30, 40, 60, 75)}.get(level, (12, 15, 35, 45, 65, 85)))
    step = 100 // math.gcd(p, 100)
    base = step * rng.randint(2, max(3, 400 // step))
    value = Fraction(p * base, 100)
    return Problem(
        "percent",
        level,
        f"What is {p} percent of {base}?",
        value,
        _PERCENT_HINTS.get(
            p, f"10 percent of {base} is {say_number(Fraction(base, 10))}. Build {p} percent from that."
        ),
        f"{p} percent means {p} out of every 100, so {p} percent of {base} is {say_number(value)}.",
    )


def _integers(level: int, rng: random.Random) -> Problem:
    a = rng.choice([n for n in range(-20, 21) if n])
    if level == 1:
        b = rng.randint(2, 20) if a < 0 else -rng.randint(2, 20)
        value = a + b
        return Problem(
            "integers",
            level,
            f"What is {_signed(a)} plus {_signed(b)}?",
            Fraction(value),
            f"Picture a number line. Start at {_signed(a)} and move {abs(b)} steps {'right' if b > 0 else 'left'}.",
            f"Starting at {_signed(a)} and moving {abs(b)} {'right' if b > 0 else 'left'} lands on {_signed(value)}.",
        )
    if level == 2:
        b = -rng.randint(2, 20)
        value = a - b
        return Problem(
            "integers",
            level,
            f"What is {_signed(a)} minus {_signed(b)}?",
            Fraction(value),
            "Subtracting a negative number is the same as adding the positive number.",
            f"{_signed(a)} minus {_signed(b)} is {_signed(a)} plus {-b}, which is {_signed(value)}.",
        )
    a, b = rng.choice([-1, 1]) * rng.randint(2, 12), -rng.randint(2, 12)
    value = a * b
    return Problem(
        "integers",
        level,
        f"What is {_signed(a)} times {_signed(b)}?",
        Fraction(value),
        "Multiply the numbers first. Two negatives make a positive; one negative makes a negative.",
        f"{abs(a)} times {abs(b)} is {abs(value)}, and the sign is {'positive' if value > 0 else 'negative'}, "
        f"so the answer is {_signed(value)}.",
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
            "Multiply before you add.",
            f"First {b} times {c} is {b * c}, then {a} plus {b * c} is {value}.",
        )
    if level == 2:
        d = rng.randint(1, (a + b) * c - 1)
        value = (a + b) * c - d
        return Problem(
            "order_of_operations",
            level,
            f"What is {a} plus {b}, in parentheses, times {c}, minus {d}?",
            Fraction(value),
            "Work out the parentheses first, then multiply, then subtract.",
            f"{a} plus {b} is {a + b}, times {c} is {(a + b) * c}, minus {d} is {value}.",
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
        "Do the multiplication and the division first, then subtract.",
        f"{a} times {b} is {a * b}, {f} divided by {e} is {f // e}, and {a * b} minus {f // e} is {_signed(value)}.",
    )


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
                f"Take {a} away from both sides.",
                f"{x + a} minus {a} is {x}, so x is {x}.",
            )
        x += a
        return Problem(
            "equations",
            level,
            f"If x minus {a} equals {x - a}, what is x?",
            Fraction(x),
            f"Add {a} to both sides.",
            f"{x - a} plus {a} is {x}, so x is {x}.",
        )
    a = rng.randint(2, 12)
    if level == 2:
        return Problem(
            "equations",
            level,
            f"If {a} times x equals {a * x}, what is x?",
            Fraction(x),
            f"Divide both sides by {a}.",
            f"{a * x} divided by {a} is {x}, so x is {x}.",
        )
    b = rng.randint(1, 20)
    return Problem(
        "equations",
        level,
        f"If {a} times x plus {b} equals {a * x + b}, what is x?",
        Fraction(x),
        f"First take {b} away from both sides, then divide by {a}.",
        f"{a * x + b} minus {b} is {a * x}, and {a * x} divided by {a} is {x}, so x is {x}.",
    )


_SPOKEN_OPERATORS = {"*": "times", "/": "divided by", "+": "plus", "-": "minus", "=": "equals"}
# An operator between two numbers (or parentheses), so "half-price" and "km/h" are left alone.
_OPERATOR_BETWEEN_NUMBERS = re.compile(r"(?<=[\d)%])\s*([*/+=-])\s*(?=[\d(.$])")


def _say_expression(text: str) -> str:
    """Math written as ``48/2 = 24`` turned into words a text-to-speech voice reads well."""
    spoken = _OPERATOR_BETWEEN_NUMBERS.sub(lambda m: f" {_SPOKEN_OPERATORS[m.group(1)]} ", text)
    return " ".join(spoken.replace("(", " ").replace(")", " ").split())


_word_problems: list[dict[str, Any]] | None = None
_word_problems_lock = threading.Lock()


def word_problems() -> list[dict[str, Any]]:
    """Return the bundled GSM8K subset (see math_data/GSM8K_LICENSE.txt)."""
    global _word_problems
    with _word_problems_lock:
        if _word_problems is None:
            lines = WORD_PROBLEMS_PATH.read_text(encoding="utf-8").splitlines()
            _word_problems = [json.loads(line) for line in lines if line.strip()]
        return _word_problems


def _word_problem(level: int, rng: random.Random) -> Problem:
    pool = [row for row in word_problems() if row["level"] == level]
    row = rng.choice(pool)
    return Problem(
        "word_problems",
        level,
        row["question"],
        Fraction(row["answer"]),
        f"Take it one step at a time. Start with {_say_expression(row['first_step'])}.",
        _say_expression(row["solution"]) if len(row["solution"]) < 300 else f"The answer is {row['answer']}.",
        source=row["id"],
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
        Skill("word_problems", "word problems", "GSM8K", _word_problem),
    )
}


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

    def skill(self, name: str) -> SkillProgress:
        """Progress for ``name``, created at level 1 on first use."""
        return self.skills.setdefault(name, SkillProgress())

    def to_json(self) -> dict[str, Any]:
        """Serialize for math_progress.json."""
        return {
            "speaker_id": self.speaker_id,
            "current_skill": self.current_skill,
            "problems_in_skill": self.problems_in_skill,
            "skills": {name: asdict(p) for name, p in self.skills.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Learner:
        """Load from math_progress.json, ignoring unknown skills and fields."""
        learner = cls(str(data.get("speaker_id", UNKNOWN)))
        if data.get("current_skill") in SKILLS:
            learner.current_skill = str(data["current_skill"])
            learner.problems_in_skill = int(data.get("problems_in_skill", 0))
        known = set(SkillProgress.__dataclass_fields__)
        for name, values in dict(data.get("skills", {})).items():
            if name in SKILLS and isinstance(values, dict):
                learner.skills[name] = SkillProgress(**{k: int(v) for k, v in values.items() if k in known})
        return learner


def record_result(progress: SkillProgress, outcome: str) -> int:
    """Apply the level rule to one finished problem; return the level change (-1, 0, or 1).

    ``outcome`` is ``first_try`` (right on the first try), ``second_try`` (right on the
    second try), or ``missed`` (not solved).
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
        self._connected_mono: float | None = None
        self._last_offer_mono: float | None = None
        self._session_results: dict[str, list[str]] = {}

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

    def next_problem(self, topic: str | None = None) -> dict[str, Any]:
        """Pick and open the next problem for whoever is speaking now."""
        with self._lock:
            speaker_id = self._speaker()
            learner = self._learner(speaker_id)
            if topic in SKILLS and topic != learner.current_skill:
                learner.current_skill, learner.problems_in_skill = str(topic), 0
            elif topic not in SKILLS and learner.problems_in_skill >= PROBLEMS_PER_SKILL:
                names = list(SKILLS)
                learner.current_skill = names[(names.index(learner.current_skill) + 1) % len(names)]
                learner.problems_in_skill = 0
            skill = SKILLS[learner.current_skill]
            level = learner.skill(skill.name).level
            problem = skill.generate(level, self._rng)
            if self._open is not None:
                study_log.record_event(
                    "math_problem_skipped", problem_id=self._open.problem_id, attempts=self._open.attempts
                )
            self._count += 1
            problem_id = f"M{self._count:03d}"
            now = time.monotonic()
            self._open = OpenProblem(problem_id, problem, speaker_id, now)
            self._last_activity_mono = now
            learner.problems_in_skill += 1
            self._save(learner)
        study_log.record_event(
            "math_problem",
            now,
            problem_id=problem_id,
            asked_to=speaker_id,
            skill=problem.skill,
            level=problem.level,
            standards=skill.standards,
            text=problem.text,
            answer=problem.answer_text,
            source=problem.source,
        )
        return {
            "problem_id": problem_id,
            "say": problem.text,
            "topic": skill.title,
            "level": problem.level,
            "instructions": "Read the problem exactly as written, then wait for the answer. "
            "Never say or hint at the answer before the child has tried.",
        }

    def check_answer(self, child_answer: str) -> dict[str, Any]:
        """Check what the child said against the open problem and update their progress."""
        with self._lock:
            open_problem = self._open
            if open_problem is None:
                return {"error": "No problem is open. Call next_math_problem first."}
            now = time.monotonic()
            self._last_activity_mono = now
            speaker_id = self._speaker()
            problem = open_problem.problem
            heard = parse_answer(child_answer)
            fields: dict[str, Any] = {
                "problem_id": open_problem.problem_id,
                "answered_by": speaker_id,
                "asked_to": open_problem.asked_to,
                "heard": child_answer,
                "parsed": None if heard is None else say_number(heard),
                "seconds_since_asked": round(now - open_problem.asked_mono, 1),
            }
            if heard is None:
                study_log.record_event("math_answer", now, **fields, attempt=None, correct=None)
                return {
                    "heard_a_number": False,
                    "instructions": "You did not hear a number. Ask them to say their answer as a number. "
                    f"If they are stuck, give this hint: {problem.hint}",
                }
            open_problem.attempts += 1
            correct = answer_matches(heard, problem.answer)
            fields.update(attempt=open_problem.attempts, correct=correct)
            if not correct and open_problem.attempts < MAX_ATTEMPTS:
                study_log.record_event("math_answer", now, **fields)
                return {
                    "correct": False,
                    "hint": problem.hint,
                    "instructions": "Say kindly that it is not quite right, give the hint in your own words, "
                    "and let them try once more. Do not say the answer.",
                }
            outcome = "missed" if not correct else "first_try" if open_problem.attempts == 1 else "second_try"
            learner = self._learner(speaker_id)
            progress = learner.skill(problem.skill)
            old_level = progress.level
            change = record_result(progress, outcome)
            self._save(learner)
            self._open = None
            self._session_results.setdefault(speaker_id, []).append(outcome)
        study_log.record_event("math_answer", now, **fields, outcome=outcome)
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
        if correct:
            result["instructions"] = (
                "Praise them briefly and specifically; you may play a happy emotion. "
                "Then ask if they want another problem."
            )
        else:
            result["explanation"] = problem.explanation
            result["instructions"] = (
                "Kindly tell them the answer and explain it in one or two short sentences using the explanation. "
                "Then ask if they want to try another one."
            )
        if change > 0:
            result["level_change"] = f"They move up to level {progress.level} in {SKILLS[problem.skill].title}."
        elif change < 0:
            result["level_change"] = f"The next {SKILLS[problem.skill].title} problems will be a bit easier."
        return result

    def stop(self, reason: str = "") -> dict[str, Any]:
        """End the practice and report how it went for each child."""
        with self._lock:
            if self._open is not None:
                study_log.record_event(
                    "math_problem_skipped", problem_id=self._open.problem_id, attempts=self._open.attempts
                )
            self._open = None
            self._last_activity_mono = None
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
        """Start timing the conversation for the first offer."""
        self._connected_mono = time.monotonic() if now is None else now

    def offer_note_if_due(self, now: float | None = None) -> str | None:
        """Return a system note asking Reachy to offer practice if it is time, else None."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if not enabled() or self._connected_mono is None or self.practice_active(now):
                return None
            if now - self._connected_mono < offer_after_s():
                return None
            if self._last_offer_mono is not None and now - self._last_offer_mono < REOFFER_AFTER_S:
                return None
            self._last_offer_mono = now
        speaker_id = self._speaker()
        ident = voice_id.identifier()
        name = ident.name_of(speaker_id) if ident is not None and speaker_id != UNKNOWN else ""
        study_log.record_event("math_offer_prompted", now, speaker_id=speaker_id)
        who = name or "the person you are talking with"
        return (
            f"Math practice: when there is a natural pause, offer {who} a few quick math problems. "
            "Ask first. If they say no, let it go and keep chatting. If they say yes, call next_math_problem."
        )


_coach = MathCoach()


def coach() -> MathCoach:
    """Return the app's math coach."""
    return _coach


def topics() -> list[str]:
    """Topic names the next_math_problem tool accepts."""
    return list(SKILLS)
