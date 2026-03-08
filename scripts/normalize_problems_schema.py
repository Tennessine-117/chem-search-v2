from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROBLEMS_PATH = DATA / "problems.json"
TAXONOMY_PATH = DATA / "taxonomy.json"


def to_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out = []
        for v in value:
            if v is None:
                continue
            text = str(v).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def uniq(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def build_type_index(taxonomy: dict) -> dict[str, tuple[str, str]]:
    idx: dict[str, tuple[str, str]] = {}
    for ch in taxonomy.get("chapters", []):
        ch_id = ch.get("id", "")
        for sec in ch.get("sections", []):
            sec_id = sec.get("id", "")
            for t in sec.get("types", []):
                tid = t.get("id", "")
                if tid:
                    idx[tid] = (ch_id, sec_id)
    return idx


def main() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    type_index = build_type_index(taxonomy)
    problems = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))

    for item in problems:
        item.pop("tags", None)
        item.pop("narrow_tag", None)
        item["solution_outline"] = item.get("solution_outline") or ""
        item["solution_memo"] = item.get("solution_memo") or ""
        item["classification_basis"] = item.get("classification_basis") or ""
        item["answer"] = item.get("answer") or ""
        item["answer_pdf"] = item.get("answer_pdf") or {}

        item["type_ids"] = uniq(to_list(item.get("type_ids")))
        primary = (item.get("primary_type_id") or "").strip()
        if primary and primary not in item["type_ids"]:
            item["type_ids"].append(primary)
        if not primary and item["type_ids"]:
            primary = item["type_ids"][0]
        item["primary_type_id"] = primary

        chapter_ids = to_list(item.get("chapter_ids"))
        section_ids = to_list(item.get("section_ids"))
        for tid in item["type_ids"]:
            meta = type_index.get(tid)
            if not meta:
                continue
            chapter_ids.append(meta[0])
            section_ids.append(meta[1])
        item["chapter_ids"] = uniq(chapter_ids)
        item["section_ids"] = uniq(section_ids)

        chapter_id = (item.get("chapter_id") or "").strip()
        section_id = (item.get("section_id") or "").strip()
        if not chapter_id and primary in type_index:
            chapter_id = type_index[primary][0]
        if not section_id and primary in type_index:
            section_id = type_index[primary][1]
        if chapter_id and chapter_id not in item["chapter_ids"]:
            item["chapter_ids"].append(chapter_id)
        if section_id and section_id not in item["section_ids"]:
            item["section_ids"].append(section_id)
        item["chapter_id"] = chapter_id
        item["section_id"] = section_id

    PROBLEMS_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"normalized={len(problems)}")


if __name__ == "__main__":
    main()
