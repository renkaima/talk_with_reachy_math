"""Rebuild src/talk_with_reachy_math/math_data/word_problems.jsonl from GSM8K.

GSM8K (https://github.com/openai/grade-school-math, MIT License) has 7,473 training
problems written for middle-school students. This keeps the ones that suit a spoken
practice session with 10- to 13-year-olds: at most 35 words, a whole-number answer of
at most 10,000, 2 to 4 calculation steps (the level), and no topics on the blocklist.
The first 100 per level, in GSM8K order, are kept.

Each calculation in a GSM8K solution (``<<48/2=24>>``) becomes a helper step: the
solution sentence it belongs to, followed by the question "What is 48 divided by 2?",
and the result as the step's answer. Reachy asks these steps one at a time when a child
needs help.

Usage: python deploy/make_word_problems.py path/to/gsm8k/train.jsonl
"""

import re
import ast
import sys
import json
import operator
from typing import Any
from decimal import Decimal
from pathlib import Path
from fractions import Fraction


OUT = Path(__file__).resolve().parent.parent / "src" / "talk_with_reachy_math" / "math_data" / "word_problems.jsonl"
PER_LEVEL = 100
MAX_WORDS = 35
BLOCKLIST = re.compile(
    r"\b(beer|wine|alcohol|drunk|vodka|whiskey|cigar\w*|smok\w*|gun\w*|shoot\w*|kill\w*|dead|die[ds]?|dying|"
    r"murder\w*|casino|gambl\w*|bet|bets|lottery|sex\w*|dating|divorc\w*|funeral|hospital|drug\w*|weapon\w*|"
    r"calori\w*|diet\w*|weigh\w*)\b",
    re.IGNORECASE,
)
ANNOTATION = re.compile(r"<<([^=>]+)=([^>]+)>>")
BINARY = re.compile(r"[\d.)]\s*[-+*/]\s*[\d.(]")  # a real calculation, not "<<4=4>>"
OPERATOR_WORDS = {"+": "plus", "-": "minus", "*": "times", "/": "divided by"}
FRACTION_WORDS = {2: "halves", 3: "thirds", 4: "fourths", 5: "fifths", 8: "eighths", 10: "tenths"}
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _value(expr: str) -> Fraction:
    """Exact value of an arithmetic expression with + - * / and parentheses."""

    def walk(node: ast.AST) -> Fraction:
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return Fraction(_OPS[type(node.op)](walk(node.left), walk(node.right)))
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(Decimal(str(node.value)))
        raise ValueError(f"not plain arithmetic: {expr}")

    return walk(ast.parse(expr, mode="eval").body)


def _say_value(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    if value.denominator in FRACTION_WORDS:
        return f"{value.numerator} {FRACTION_WORDS[value.denominator]}"
    return str(float(value))


def speak(expr: str) -> str:
    """'(60+68+64)/3' -> '60 plus 68 plus 64, then divided by 3'; '180-(40+40)' -> '180 minus 80'.

    Spoken math has no parentheses, so a bracketed group after an operator is replaced by
    its value, and a bracketed group at the start is closed with a pause and "then".
    """
    expr = expr.replace(" ", "")
    expr = re.sub(r"(?<=[-+*/])\(([^()]+)\)", lambda m: _say_value(_value(m.group(1))), expr)
    expr = re.sub(r"^\(([^()]+)\)(?=[-+*/])", r"\1,then", expr)
    expr = expr.strip("()")
    spoken = re.sub(r"(?<=[\d.,)a-z])([-+*/])(?=[\d.(a-z])", lambda m: f" {OPERATOR_WORDS[m.group(1)]} ", expr)
    return spoken.replace(",then", ", then")


def _sentence(text: str) -> str:
    """End a GSM8K solution line with a full stop, so Reachy pauses between lines."""
    text = text.strip()
    return text if not text or text[-1] in ".?!" else f"{text}."


def steps_of(solution: str) -> list[dict[str, Any]]:
    """One helper step per calculation; sentences without one lead into the next step."""
    steps: list[dict[str, Any]] = []
    lead: list[str] = []
    for line in (part.strip() for part in solution.splitlines()):
        if not line:
            continue
        match = ANNOTATION.search(line)
        if match is None or not BINARY.search(match.group(1)):
            lead.append(_sentence(ANNOTATION.sub("", line)))
            continue
        expr, result = match.group(1), match.group(2)
        before = line[: match.start()]
        after = re.sub(r"^[\d.,]+", "", line[match.end() :])
        shown = before.rstrip().rstrip("$").rstrip()
        if shown.endswith("="):  # "Natalia sold 48/2 = <<48/2=24>>24 clips" keeps the written calculation
            context = shown[:-1].rstrip() + after
        else:  # "She has <<3*4=12>>12 apples" gets the calculation put in
            context = before + expr + after
        context = _sentence(ANNOTATION.sub("", context))
        steps.append(
            {
                "ask": " ".join([*lead, context, f"What is {speak(expr)}?"]),
                "answer": str(Decimal(result).normalize()) if "." in result else result,
            }
        )
        if _value(expr) != Fraction(Decimal(result)):
            raise ValueError(f"step result does not match its calculation: {line}")
        lead = []
    return steps


def main() -> int:
    """Filter GSM8K and write the subset, one JSON object per line."""
    kept: dict[int, list[dict[str, object]]] = {2: [], 3: [], 4: []}
    for line_no, line in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        question, solution = row["question"].strip(), row["answer"]
        final = solution.split("####")[-1].strip().replace(",", "")
        level = len(re.findall(r"<<([^=>]+)=", solution))
        if level not in kept or len(kept[level]) >= PER_LEVEL:
            continue
        if not re.fullmatch(r"\d+", final) or int(final) > 10000 or len(question.split()) > MAX_WORDS:
            continue
        if BLOCKLIST.search(question) or BLOCKLIST.search(solution):
            continue
        work = solution.split("####")[0]
        kept[level].append(
            {
                "id": f"gsm8k-train-{line_no}",
                "level": level - 1,
                "question": question,
                "answer": int(final),
                "steps": steps_of(work),
                "solution": " ".join(
                    _sentence(part) for part in ANNOTATION.sub("", work).splitlines() if part.strip()
                ),
            }
        )
    rows = [row for level in sorted(kept) for row in kept[level]]
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} problems to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
