"""Every sentence a child hears in the math games is short and uses words most 4th graders know.

The word list is the Dale-Chall list of about 3,000 words that most 4th graders know
(Chall & Dale, 1995), as shipped with textstat. A few math words from grade 5 to 7 lessons
and a few words for the story themes are added below. docs/LEARNING_DESIGN.md explains
why these limits matter when a child only hears a problem and cannot read it.
"""

import re
import random
from importlib.resources import files

from talk_with_reachy_math import math_games, math_practice


MAX_WORDS = 15  # per sentence, numbers included

# Words that math lessons for grades 5 to 7 teach, so children know them from school.
MATH_WORDS = {
    "math",
    "plus",
    "minus",
    "times",
    "divided",
    "percent",
    "fraction",
    "decimal",
    "digit",
    "negative",
    "positive",
    "parentheses",
    "zero",
    "x",
    "equals",
    # names of bottom numbers that are not on the list (third, fourth, fifth, sixth, eighth are)
    "halves",
    "seventh",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "fifteenth",
    "sixteenth",
    "twentieth",
    "thirtieth",
    "fortieth",
    "sixtieth",
    "hundredth",
}
# Everyday words of the story themes, and short forms Reachy uses when it talks.
KID_WORDS = {
    "pizza",
    "soccer",
    "dinosaur",
    "alien",
    "video",
    "baby",
    "clue",
    "let's",
    "here's",
    "i'm",
    "can't",
}


def _known_words() -> set[str]:
    text = files("textstat").joinpath("resources/en/easy_words.txt").read_text(encoding="utf-8")
    return {w.strip().lower() for w in text.split()} | MATH_WORDS | KID_WORDS


KNOWN = _known_words()
_ENDINGS = (("s", ""), ("es", ""), ("ies", "y"), ("ed", ""), ("ed", "e"), ("d", ""), ("ing", ""), ("ing", "e"))
_ENDINGS += (("er", ""), ("er", "e"), ("est", ""), ("est", "e"), ("ly", ""), ("'s", ""))


def is_known(word: str) -> bool:
    """Whether ``word`` or its plain form (dogs: dog, bigger: big, adding: add) is on the list."""
    w = word.lower()
    if w in KNOWN:
        return True
    for ending, add in _ENDINGS:
        if w.endswith(ending) and w[: -len(ending)] + add in KNOWN:
            return True
        doubled = w[: -len(ending)]  # bigger -> bigg -> big
        if w.endswith(ending) and len(doubled) > 2 and doubled[-1] == doubled[-2] and doubled[:-1] in KNOWN:
            return True
    return False


def sentences(text: str) -> list[str]:
    """Split on sentence ends, but not on the point in a number such as 0.75."""
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def _problems() -> list[math_practice.Problem]:
    rng = random.Random(0)
    found = []
    for level in (1, 2, 3):
        for skill in math_practice.SKILLS.values():
            found += [skill.generate(level, rng) for _ in range(15)]
        for make in math_games.MAKERS.values():
            for theme in math_games.THEMES.values():
                start = rng.randrange(1000)
                for position in range(1, 6):
                    turn = math_games.Turn(position, lambda _name, level=level: level, theme, start, rng)
                    found.append(make(turn))
    return found


def heard_texts() -> list[str]:
    """Everything the app gives Reachy to say word for word."""
    texts = list(math_games.TITLES.values())
    for theme in math_games.THEMES.values():
        texts += [theme.start, theme.end]
    for problem in _problems():
        texts += [problem.text, problem.explanation, *(step.ask for step in problem.steps)]
        if problem.game == math_practice.RIDDLES:
            texts.append(math_games.riddle_miss(problem, problem.answer + 1) or "")
    return texts


TEXTS = heard_texts()


def test_the_word_check_knows_plain_forms() -> None:
    """Plurals, past tense, and -ing forms of list words count; grown-up math words do not."""
    assert all(is_known(w) for w in ("dogs", "boxes", "puppies", "added", "adding", "bigger", "closest", "Let's"))
    assert not any(is_known(w) for w in ("decompose", "distributive", "operation", "variable", "quotient"))


def test_every_sentence_is_short() -> None:
    """No sentence a child hears is longer than 15 words."""
    long = sorted({s for t in TEXTS for s in sentences(t) if len(s.split()) > MAX_WORDS}, key=len)
    assert not long, f"{len(long)} sentences are too long, for example: {long[:5]}"


def test_every_word_is_one_children_know() -> None:
    """Every word is on the 4th-grade list, or is a math word from school, or a story theme word."""
    unknown: dict[str, str] = {}
    for text in TEXTS:
        for word in re.findall(r"[A-Za-z]+(?:'[a-z]+)?", text):
            if not is_known(word):
                unknown.setdefault(word.lower(), text)
    assert not unknown, f"{len(unknown)} words to replace: " + "; ".join(f"{w!r} in {t!r}" for w, t in unknown.items())
