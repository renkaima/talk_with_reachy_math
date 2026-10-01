"""Rebuild src/talk_with_reachy_math/math_data/word_problems.jsonl from GSM8K.

GSM8K (https://github.com/openai/grade-school-math, MIT License) has 7,473 training
problems written for middle-school students. This keeps the ones that suit a spoken
practice session with 10- to 13-year-olds: at most 35 words, a whole-number answer of
at most 10,000, 2 to 4 calculation steps (the level), and no topics on the blocklist.
The first 100 per level, in GSM8K order, are kept.

Usage: python deploy/make_word_problems.py path/to/gsm8k/train.jsonl
"""

import re
import sys
import json
from pathlib import Path


OUT = Path(__file__).resolve().parent.parent / "src" / "talk_with_reachy_math" / "math_data" / "word_problems.jsonl"
PER_LEVEL = 100
MAX_WORDS = 35
BLOCKLIST = re.compile(
    r"\b(beer|wine|alcohol|drunk|vodka|whiskey|cigar\w*|smok\w*|gun\w*|shoot\w*|kill\w*|dead|die[ds]?|dying|"
    r"murder\w*|casino|gambl\w*|bet|bets|lottery|sex\w*|dating|divorc\w*|funeral|hospital|drug\w*|weapon\w*|"
    r"calori\w*|diet\w*|weigh\w*)\b",
    re.IGNORECASE,
)


def main() -> int:
    """Filter GSM8K and write the subset, one JSON object per line."""
    kept: dict[int, list[dict[str, object]]] = {2: [], 3: [], 4: []}
    for line_no, line in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        question, solution = row["question"].strip(), row["answer"]
        final = solution.split("####")[-1].strip().replace(",", "")
        steps = re.findall(r"<<([^=>]+)=", solution)
        level = len(steps)
        if level not in kept or len(kept[level]) >= PER_LEVEL:
            continue
        if not re.fullmatch(r"\d+", final) or int(final) > 10000 or len(question.split()) > MAX_WORDS:
            continue
        if BLOCKLIST.search(question) or BLOCKLIST.search(solution):
            continue
        work = re.sub(r"<<[^>]*>>", "", solution.split("####")[0]).strip()
        kept[level].append(
            {
                "id": f"gsm8k-train-{line_no}",
                "level": level - 1,
                "question": question,
                "answer": int(final),
                "first_step": steps[0].strip(),
                "solution": " ".join(part.strip() for part in work.splitlines() if part.strip()),
            }
        )
    rows = [row for level in sorted(kept) for row in kept[level]]
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} problems to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
