from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_PATH = ROOT / "data" / "search_eval_30.json"
sys.path.insert(0, str(ROOT))

import app


def topk_hit(results: list[dict], expected_id: str, k: int) -> bool:
    return any(r.get("id") == expected_id for r in results[:k])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", default=str(DEFAULT_EVAL_PATH))
    args = parser.parse_args()

    eval_path = Path(args.eval)
    cases = json.loads(eval_path.read_text(encoding="utf-8"))
    if not cases:
        raise SystemExit("No eval cases.")

    top1 = 0
    top3 = 0
    top5 = 0
    rows = []

    for case in cases:
        query = case.get("query", "")
        source = case.get("source", "")
        expected = case.get("expected_problem_id", "")
        results = app.search_problems(query, source_filter=source)

        h1 = topk_hit(results, expected, 1)
        h3 = topk_hit(results, expected, 3)
        h5 = topk_hit(results, expected, 5)
        top1 += int(h1)
        top3 += int(h3)
        top5 += int(h5)

        rows.append(
            {
                "id": case.get("id"),
                "query": query,
                "expected": expected,
                "top1": h1,
                "top3": h3,
                "top5": h5,
                "pred_top5": [r.get("id", "") for r in results[:5]],
            }
        )

    n = len(cases)
    print(f"cases={n}")
    print(f"Top1: {top1}/{n} ({top1/n:.1%})")
    print(f"Top3: {top3}/{n} ({top3/n:.1%})")
    print(f"Top5: {top5}/{n} ({top5/n:.1%})")

    failed = [r for r in rows if not r["top5"]]
    print(f"Top5 miss: {len(failed)}")
    for row in failed[:10]:
        print(f"- {row['id']} expected={row['expected']} pred={row['pred_top5']}")


if __name__ == "__main__":
    main()
