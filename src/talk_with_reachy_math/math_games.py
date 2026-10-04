"""Math games for children aged about 10 to 13, played by voice.

A round has five problems from one game, and the child picks the game:

- ``story``: a story adventure in five parts about something the child likes. Each part
  needs one math problem to go on.
- ``fix_my_mistake``: Reachy shows its own work with a common mistake in it, and the child
  finds the real answer.
- ``riddles``: "I'm thinking of a number between 20 and 30. It is odd..."
- ``closest_guess``: the child and Reachy both guess an answer; the closer guess wins.
- ``quick_math``: plain problems, one topic at a time (built in ``math_practice``).

As in quick math, the app makes every problem and checks every answer; the model only reads
the text and passes on what the child said. Every sentence a child hears is short and uses
words that most 4th graders know (``tests/test_kid_words.py`` checks this).
docs/LEARNING_DESIGN.md explains the research behind each game.
"""

from __future__ import annotations
import random
from fractions import Fraction
from dataclasses import replace, dataclass
from collections.abc import Callable

from talk_with_reachy_math.math_practice import (
    STORY,
    RIDDLES,
    QUICK_MATH,
    CLOSEST_GUESS,
    FIX_MY_MISTAKE,
    _DENOMINATOR_WORDS,
    Clue,
    Step,
    Problem,
    _signed,
    say_number,
    say_fraction,
    divide_problem,
    fraction_steps,
    decimal_problem,
    percent_numbers,
    percent_problem,
    multiply_problem,
    fraction_of_problem,
    _proper_fraction_words,
)


# How Reachy names each game when it lets the child pick.
TITLES = {
    STORY: "a story adventure",
    FIX_MY_MISTAKE: "fix my mistakes",
    RIDDLES: "number riddles",
    CLOSEST_GUESS: "a closest guess game",
    QUICK_MATH: "quick math",
}
# How Reachy explains a game the first time a child plays it, before the first problem.
_TAKE_YOUR_TIME = "Take your time, and say help if you get stuck."
HOW_TO_PLAY = {
    STORY: "Here is how it works. I tell a story in five parts. Each part has a math question. "
    f"Get it right, and the story goes on! {_TAKE_YOUR_TIME}",
    FIX_MY_MISTAKE: "Here is how it works. I did some math, but I made mistakes. I tell you my answer. "
    f"You find the right answer. Then you tell me what I did wrong! {_TAKE_YOUR_TIME}",
    RIDDLES: "Here is how it works. I think of a secret number and give you clues. "
    f"You find the number that fits every clue! {_TAKE_YOUR_TIME}",
    CLOSEST_GUESS: "Here is how it works. I ask a question, and we both guess the answer. "
    "You guess first, then me. The closer guess wins! Round the numbers to guess fast.",
    QUICK_MATH: f"Here is how it works. I ask a math question, and you say the answer. {_TAKE_YOUR_TIME}",
}
# The one line Reachy says instead when the child has played the game before.
REMINDERS = {
    STORY: "Answer each part to make the story go on.",
    FIX_MY_MISTAKE: "Find the right answer, then tell me what I did wrong.",
    RIDDLES: "Find the secret number that fits every clue.",
    CLOSEST_GUESS: "We both guess, and the closer guess wins.",
    QUICK_MATH: "Say your answer when you are ready.",
}
# Common Core standards practiced by the games with a level of their own (the others use their topics').
STANDARDS = {RIDDLES: "4.OA.4", CLOSEST_GUESS: "4.OA.3, 5.NBT.5"}


@dataclass(frozen=True)
class Theme:
    """What a story or guessing game is about, in words a child knows."""

    name: str
    start: str  # the first line of the story
    end: str  # the last line, said when the round is over
    things: str  # what the problems count, plural
    friends: str  # whom the things are shared with, plural
    bag: str  # what holds the things
    bags: str
    item: str  # something to buy at a shop


THEMES: dict[str, Theme] = {
    t.name: t
    for t in (
        Theme(
            "space",
            "Our rocket is ready to fly to the moon!",
            "We made it to the moon! You are a great captain!",
            "moon rocks",
            "aliens",
            "box",
            "boxes",
            "space map",
        ),
        Theme(
            "dogs",
            "Today we open a new dog park!",
            "The dog park is open, and every puppy is happy!",
            "dog treats",
            "puppies",
            "bag",
            "bags",
            "dog bed",
        ),
        Theme(
            "soccer",
            "Our soccer team has a big game today!",
            "We won the big game! What a team!",
            "soccer balls",
            "players",
            "bag",
            "bags",
            "team shirt",
        ),
        Theme(
            "dinosaurs",
            "We are going to look for dinosaur eggs!",
            "We found the dinosaur nest! What an adventure!",
            "dinosaur eggs",
            "baby dinosaurs",
            "basket",
            "baskets",
            "dinosaur book",
        ),
        Theme(
            "pizza",
            "Today we open our own pizza shop!",
            "Everyone loves our pizza shop! Great job!",
            "pizza slices",
            "hungry kids",
            "box",
            "boxes",
            "pizza oven",
        ),
        Theme(
            "ocean",
            "We dive down to find a lost ship!",
            "We found the lost ship and its gold!",
            "shells",
            "fish",
            "bag",
            "bags",
            "diving mask",
        ),
        Theme(
            "video_games",
            "We are building a castle in our video game!",
            "Our castle is done, and it looks great!",
            "gold coins",
            "players",
            "chest",
            "chests",
            "magic sword",
        ),
    )
}


@dataclass(frozen=True)
class Turn:
    """What a game needs to make the next problem of a round."""

    position: int  # 1 to 5 within the round
    level_of: Callable[[str], int]  # the child's level for a topic or game
    theme: Theme
    start: int  # a random number picked when the round started, so rounds differ
    rng: random.Random


# ---------------------------------------------------------------------------
# Story adventure: five parts, each with one problem


# Story numbers stay small enough to work out in your head while listening.
_PACK = {1: (range(12, 50), range(3, 10)), 2: (range(51, 100), range(6, 10)), 3: (range(101, 300), range(3, 10))}
_SHARE = {1: (range(12, 31), range(3, 10)), 2: (range(12, 100), range(3, 10)), 3: (range(11, 40), range(11, 26))}


def _part_pack(turn: Turn) -> Problem:
    t, level, rng = turn.theme, turn.level_of("multiply"), turn.rng
    many, each = _PACK[level]
    a, b = rng.choice([n for n in many if n % 10]), rng.choice(each)
    text = f"{t.start} We pack {b} {t.bags}. Each {t.bag} holds {a} {t.things}. How many {t.things} is that?"
    return replace(multiply_problem(level, a, b), text=text)


def _part_share(turn: Turn) -> Problem:
    t, level, rng = turn.theme, turn.level_of("divide"), turn.rng
    answers, divisors = _SHARE[level]
    q, d = rng.choice(answers), rng.choice(divisors)
    text = (
        f"On the way, we meet {d} {t.friends}. We share {q * d} {t.things} with them, the same for each. "
        f"How many {t.things} does each one get?"
    )
    return replace(divide_problem(level, q, d), text=text)


def _part_fix(turn: Turn) -> Problem:
    t, level, rng = turn.theme, turn.level_of("fractions"), turn.rng
    d = rng.choice({1: (2, 3, 4, 5, 10), 2: (3, 4, 5, 6, 8)}.get(level, (6, 8, 10, 12)))
    x = Fraction(1 if level == 1 else rng.randint(1, d - 1), d)
    whole = d * rng.randint(3, 12 if level == 3 else 10)
    text = (
        f"Oh no, we are stuck! To get going, we need {say_fraction(x)} of our {whole} {t.things}. "
        f"How many {t.things} is that?"
    )
    return replace(fraction_of_problem(level, x, whole), text=text)


def _part_shop(turn: Turn) -> Problem:
    t, level = turn.theme, turn.level_of("percent")
    p, base = percent_numbers(level, turn.rng)
    text = (
        f"Next, we stop at a shop. A {t.item} costs {base} coins. Today it is {p} percent off! "
        "How many coins do we save?"
    )
    return replace(percent_problem(level, p, base), text=text)


def _part_count(turn: Turn) -> Problem:
    t, level, rng = turn.theme, turn.level_of("order_of_operations"), turn.rng
    b = rng.randint(2, 9) if level < 3 else rng.randint(6, 12)
    c = rng.randint(2, 9) if level == 1 else rng.randint(11, 19)
    a = rng.randint(2, 12) if level == 1 else rng.randint(11, 30)
    value = a + b * c
    return Problem(
        "order_of_operations",
        level,
        f"Last stop! We have {b} {t.bags} with {c} {t.things} in each, and {a} more {t.things}. "
        f"How many {t.things} do we have now?",
        Fraction(value),
        (
            Step(f"First the {t.bags}. What is {b} times {c}?", Fraction(b * c)),
            Step(f"Now add the {a} more. What is {b * c} plus {a}?", Fraction(value)),
        ),
        f"{b} {t.bags} of {c} make {b * c}. {b * c} plus {a} more makes {value}.",
    )


_STORY_PARTS = (_part_pack, _part_share, _part_fix, _part_shop, _part_count)


def _story(turn: Turn) -> Problem:
    part = _STORY_PARTS[(turn.position - 1) % len(_STORY_PARTS)](turn)
    return replace(part, game=STORY, theme=turn.theme.name)


# ---------------------------------------------------------------------------
# Fix my mistake: Reachy's work has one common mistake in it

_CHECK = "Can you check my work?"
_ASK = "What is the real answer?"


def _mistake_fractions(turn: Turn) -> Problem:
    level, rng = turn.level_of("fractions"), turn.rng
    pool = (2, 3, 4) if level == 1 else (2, 3, 4, 5, 6) if level == 2 else (2, 3, 4, 5, 6, 8)
    while True:
        d1, d2 = rng.sample(pool, 2)
        x = Fraction(1 if level == 1 else rng.randint(1, d1 - 1), d1)
        y = Fraction(1 if level == 1 else rng.randint(1, d2 - 1), d2)
        top, bottom = x.numerator + y.numerator, x.denominator + y.denominator
        if bottom in _DENOMINATOR_WORDS and top < bottom:
            break
    steps, explanation = fraction_steps(x, y, "plus")
    wrong = _proper_fraction_words(top, bottom)
    return Problem(
        "fractions",
        level,
        f"{_CHECK} I tried {say_fraction(x)} plus {say_fraction(y)}. I added the top numbers and the bottom "
        f"numbers. I got {wrong}. {_ASK}",
        x + y,
        steps,
        f"My mistake: the bottom numbers must be the same before we add. {explanation}",
        reachy_answer=Fraction(top, bottom),
    )


def _mistake_decimals(turn: Turn) -> Problem:
    level, rng = turn.level_of("decimals"), turn.rng
    whole_x, whole_y = (0, 0) if level == 1 else (rng.randint(1, 9), rng.randint(1, 9))
    tenths = rng.randint(1, 8)
    hundredths = rng.choice([n for n in range(11, 100 - tenths * 10) if n % 10])
    x, y = whole_x + Fraction(tenths, 10), whole_y + Fraction(hundredths, 100)
    wrong = whole_x + whole_y + Fraction(tenths + hundredths, 100)  # 0.5 + 0.25 "=" 0.30
    problem = decimal_problem(level, x, y, "plus")
    return replace(
        problem,
        text=f"{_CHECK} I tried {say_number(x)} plus {say_number(y)}. After the point, I added {tenths} and "
        f"{hundredths} to get {tenths + hundredths}. So I got {whole_x + whole_y}.{tenths + hundredths:02d}. {_ASK}",
        explanation=f"My mistake: {say_number(x)} is the same as {say_number(x)}0, so it has {tenths * 10} "
        f"hundredths, not {tenths}. {problem.explanation}",
        reachy_answer=wrong,
    )


def _mistake_order(turn: Turn) -> Problem:
    level, rng = turn.level_of("order_of_operations"), turn.rng
    a, b, c = rng.randint(2, 9 if level == 1 else 20), rng.randint(2, 9), rng.randint(2, 9 if level < 3 else 12)
    value, wrong = a + b * c, (a + b) * c
    return Problem(
        "order_of_operations",
        level,
        f"{_CHECK} I tried {a} plus {b} times {c}. I did {a} plus {b} first, then times {c}. I got {wrong}. {_ASK}",
        Fraction(value),
        (
            Step(f"Times comes before plus. What is {b} times {c}?", Fraction(b * c)),
            Step(f"Now add {a}. What is {a} plus {b * c}?", Fraction(value)),
        ),
        f"My mistake: I did plus first, but times comes before plus. {b} times {c} is {b * c}. "
        f"Then {a} plus {b * c} is {value}.",
        reachy_answer=Fraction(wrong),
    )


def _mistake_integers(turn: Turn) -> Problem:
    level, rng = turn.level_of("integers"), turn.rng
    a = rng.randint(2, 15) if level == 1 else rng.choice([-1, 1]) * rng.randint(2, 15)
    b = rng.randint(2, 12)
    value, wrong = a + b, a - b
    return Problem(
        "integers",
        level,
        f"{_CHECK} I tried {_signed(a)} minus negative {b}. I just took away {b}. I got {_signed(wrong)}. {_ASK}",
        Fraction(value),
        (Step(f"Taking away a negative is the same as adding. What is {_signed(a)} plus {b}?", Fraction(value)),),
        f"My mistake: taking away a negative is the same as adding. So the answer is {_signed(a)} plus {b}. "
        f"That makes {_signed(value)}.",
        reachy_answer=Fraction(wrong),
    )


def _mistake_multiply(turn: Turn) -> Problem:
    level, rng = turn.level_of("multiply"), turn.rng
    a = rng.choice([n for n in (range(12, 50) if level == 1 else range(51, 100)) if n % 10])
    b = rng.randint(3, 9) if level == 1 else rng.randint(6, 9)
    tens = a // 10 * 10
    problem = multiply_problem(level, a, b)
    return replace(
        problem,
        text=f"{_CHECK} I tried {a} times {b}. I did {tens} times {b} and got {tens * b}. "
        f"So I said {tens * b}. {_ASK}",
        explanation=f"My mistake: I forgot the {a % 10}. {problem.explanation}",
        reachy_answer=Fraction(tens * b),
    )


def _mistake_percent(turn: Turn) -> Problem:
    level, rng = turn.level_of("percent"), turn.rng
    p = {1: 10, 2: 20}.get(level, 25)
    while True:
        base = rng.randint(3, 20) * (20 if p == 25 else 10)
        if base - p != base * p // 100:
            break
    problem = percent_problem(level, p, base)
    return replace(
        problem,
        text=f"{_CHECK} I tried {p} percent of {base}. I just took away {p}. I got {base - p}. {_ASK}",
        explanation=f"My mistake: percent means out of 100, so I can't just take away {p}. {problem.explanation}",
        reachy_answer=Fraction(base - p),
    )


def _mistake_equation(turn: Turn) -> Problem:
    level, rng = turn.level_of("equations"), turn.rng
    x, a = rng.randint(2, 15), rng.randint(2, 12)
    if level == 1:
        total, wrong = x + a, x + 2 * a
        text = f"{_CHECK} The puzzle is x plus {a} equals {total}. I added {a} and {total}. I got {wrong}."
        step = Step(f"Something plus {a} makes {total}. What is {total} minus {a}?", Fraction(x))
        explanation = f"My mistake: I should take {a} away, not add it. {total} minus {a} is {x}."
    else:
        total, wrong = a * x, a * a * x
        text = f"{_CHECK} The puzzle is {a} times x equals {total}. I did {a} times {total}. I got {wrong}."
        step = Step(f"{a} times something makes {total}. What is {total} divided by {a}?", Fraction(x))
        explanation = f"My mistake: I should divide by {a}, not times {a}. {total} divided by {a} is {x}."
    return Problem(
        "equations",
        level,
        f"{text} What is x really?",
        Fraction(x),
        (step,),
        explanation,
        reachy_answer=Fraction(wrong),
    )


_MISTAKES = (
    _mistake_fractions,
    _mistake_order,
    _mistake_multiply,
    _mistake_decimals,
    _mistake_integers,
    _mistake_percent,
    _mistake_equation,
)


def _fix_my_mistake(turn: Turn) -> Problem:
    mistake = _MISTAKES[(turn.start + turn.position) % len(_MISTAKES)]  # five different mistakes per round
    return replace(mistake(turn), game=FIX_MY_MISTAKE)


# ---------------------------------------------------------------------------
# Number riddles


def _digit_sum(n: int) -> int:
    return sum(int(c) for c in str(abs(n)))


_RIDDLE_RANGES = {1: (range(10, 51, 10), 10), 2: (range(10, 81, 10), 20), 3: (range(20, 121, 10), 30)}
_TIMES_TABLES = {1: (3, 4, 5), 2: (3, 4, 6, 7, 9), 3: (6, 7, 8, 9, 11, 12)}


def _multiple_of(k: int) -> Callable[[int], bool]:
    return lambda n: n % k == 0


def _between(lo: int, hi: int) -> Callable[[int], bool]:
    return lambda n: lo < n < hi


def _riddle_clues(t: int, level: int) -> list[Clue]:
    """Every clue that is true for the secret number ``t``."""
    odd = t % 2
    clues = [
        Clue("It is odd." if odd else "It is even.", lambda n: n % 2 == odd, f"{t} is {'odd' if odd else 'even'}")
    ]
    for k in _TIMES_TABLES[level]:
        if t % k == 0:
            clues.append(Clue(f"It is in the {k} times table.", _multiple_of(k), f"{k} times {t // k} is {t}"))
    s = _digit_sum(t)
    clues.append(Clue(f"Its digits add up to {s}.", lambda n: _digit_sum(n) == s, f"{' plus '.join(str(t))} is {s}"))
    if level > 1:
        last = t % 10
        clues.append(Clue(f"Its last digit is {last}.", lambda n: n % 10 == last, f"{t} ends in {last}"))
    return clues


def _riddles(turn: Turn) -> Problem:
    level, rng = turn.level_of(RIDDLES), turn.rng
    starts, width = _RIDDLE_RANGES[level]
    while True:
        lo = rng.choice(starts)
        hi = lo + width
        t = rng.randint(lo + 1, hi - 1)
        between = Clue(f"It is between {lo} and {hi}.", _between(lo, hi), f"{t} is between {lo} and {hi}")
        options = _riddle_clues(t, level)
        rng.shuffle(options)
        left, chosen = list(range(lo + 1, hi)), []
        for clue in options:
            fewer = [n for n in left if clue.fits(n)]
            if len(fewer) < len(left):
                chosen.append(clue)
                left = fewer
            if len(left) == 1:
                break
        if len(left) == 1 and 2 <= len(chosen) <= 3:
            break
    last = f"Its last digit is {t % 10}."
    others = [c.text for c in options if c not in chosen]
    extra = last if all(c.text != last for c in chosen) else others[0] if others else f"It is bigger than {t - 3}."
    because = " ".join(f"{c.because[0].upper()}{c.because[1:]}." for c in (between, *chosen))
    return Problem(
        RIDDLES,
        level,
        f"I'm thinking of a number between {lo} and {hi}. {' '.join(c.text for c in chosen)} What is my number?",
        Fraction(t),
        (
            Step(f"Here is one more clue. {extra} What is my number?", Fraction(t)),
            Step(f"Last clue: it is 1 more than {t - 1}. What is my number?", Fraction(t)),
        ),
        f"My number is {t}. {because}",
        game=RIDDLES,
        clues=(between, *chosen),
    )


def riddle_miss(problem: Problem, guess: Fraction) -> str | None:
    """Say which clue a wrong riddle guess does not fit, such as "24 is not odd."; None if it fits them all."""
    if guess.denominator != 1:
        return "My number is a whole number."
    n = int(guess)
    for clue in problem.clues:
        if not clue.fits(n):
            return f"{n} does not fit this clue: {clue.text[0].lower()}{clue.text[1:]}"
    return None


# ---------------------------------------------------------------------------
# Closest guess: the child guesses first, then Reachy; the closer guess wins


def _near(round_to: int, low: int, high: int, rng: random.Random, off: int = 2) -> tuple[int, int]:
    """Return a number a little away from a round number, and that round number: (49, 50)."""
    rounded = rng.randrange(low, high + 1, round_to)
    return rounded + rng.choice([d for d in range(-off, off + 1) if d]), rounded


def _closest_guess(turn: Turn) -> Problem:
    t, level, rng = turn.theme, turn.level_of(CLOSEST_GUESS), turn.rng
    a, ra = _near(100, 200, 900, rng, 4) if level == 3 else _near(10, 20, 90, rng)
    if level == 1:
        b = rb = rng.randint(3, 9)
        rough = f"{a} is close to {ra}. {ra} times {b} is {ra * b}."
    else:
        b, rb = _near(10, 20, 90, rng)
        rough = f"{a} is close to {ra}, and {b} is close to {rb}. {ra} times {rb} is {ra * rb}."
    exact = a * b
    step = 10 if exact < 1000 else 100
    reachy = round(exact * rng.choice((0.75, 0.8, 1.2, 1.25)) / step) * step
    return Problem(
        CLOSEST_GUESS,
        level,
        f"{b} {t.bags} have {a} {t.things} in each. About how many {t.things} is that? "
        "Just guess, then I will guess too.",
        Fraction(exact),
        (),
        f"{rough} So the answer is close to {ra * rb}.",
        game=CLOSEST_GUESS,
        reachy_answer=Fraction(reachy),
        theme=t.name,
    )


MAKERS: dict[str, Callable[[Turn], Problem]] = {
    STORY: _story,
    FIX_MY_MISTAKE: _fix_my_mistake,
    RIDDLES: _riddles,
    CLOSEST_GUESS: _closest_guess,
}
