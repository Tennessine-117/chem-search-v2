from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROBLEMS_PATH = DATA / "problems.json"
TAXONOMY_PATH = DATA / "taxonomy.json"
OUT_PATH = DATA / "search_eval_30.json"


def load_type_name_map(taxonomy: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for ch in taxonomy.get("chapters", []):
        for sec in ch.get("sections", []):
            for t in sec.get("types", []):
                out[t.get("id", "")] = t.get("name", "")
    return out


def main() -> None:
    problems = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    type_name = load_type_name_map(taxonomy)

    # One representative per type from Kawai, up to 30 queries.
    selected: list[dict] = []
    seen_types: set[str] = set()
    for item in problems:
        if item.get("source") != "2025_kawai":
            continue
        primary = (item.get("primary_type_id") or "").strip()
        if not primary or primary in seen_types:
            continue
        seen_types.add(primary)
        title = (item.get("title") or "").strip()
        statement = (item.get("statement") or "").strip().replace("\n", " ")
        hint = statement[:36].strip()
        if not hint:
            hint = type_name.get(primary, primary)
        selected.append(
            {
                "id": f"eval_{len(selected)+1:02d}",
                "query": f"{title} に近い問題を探して {hint}",
                "expected_problem_id": item["id"],
                "source": "2025_kawai",
                "notes": f"primary_type={primary}",
            }
        )
        if len(selected) >= 30:
            break

    OUT_PATH.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written={OUT_PATH} count={len(selected)}")


if __name__ == "__main__":
    main()
