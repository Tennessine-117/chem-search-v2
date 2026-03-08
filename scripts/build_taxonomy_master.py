from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_PATH = DATA / "taxonomy.json"
CHAPTER_DIR = DATA / "taxonomy_chapters"

CHAPTER_RE = re.compile(r"^CHAPTER\d{2}$")
SECTION_RE = re.compile(r"^SECTION\d{2}$")
TYPE_RE = re.compile(r"^TYPE\d{3}$")

TEXT_REPLACEMENTS = {
    "⇒": "→",
    "⟶": "→",
    "->": "→",
    "－": "-",
    "＝": "=",
}


def normalize_text(text: str) -> str:
    s = text.replace("\u3000", " ")
    for src, dst in TEXT_REPLACEMENTS.items():
        s = s.replace(src, dst)
    s = re.sub(r"\s+", " ", s).strip()
    # Common notation normalization.
    s = s.replace("ＰＨ", "pH").replace("ｐＨ", "pH").replace("ｐH", "pH")
    s = s.replace("Ｋｐ", "Kp").replace("Ｋｃ", "Kc")
    s = s.replace("ＣＯＤ", "COD").replace("ＤＯ", "DO")
    return s


def normalize_obj(value):
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_obj(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_obj(v) for k, v in value.items()}
    return value


def load_chapter_docs() -> list[dict]:
    if CHAPTER_DIR.exists():
        docs = []
        for path in sorted(CHAPTER_DIR.glob("*.json")):
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        if docs:
            return docs
    # Fallback: use current taxonomy as source.
    base = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return base.get("chapters", [])


def chapter_doc_to_chapter(ch_doc: dict) -> dict:
    if "id" in ch_doc and "sections" in ch_doc:
        return {
            "id": ch_doc["id"],
            "name": ch_doc.get("name", ""),
            "sections": ch_doc.get("sections", []),
        }
    if "chapter_id" in ch_doc and "types" in ch_doc:
        sections: dict[str, dict] = {}
        for t in ch_doc.get("types", []):
            sec_id = t.get("section_id", "")
            sec_name = t.get("section_name", "")
            sections.setdefault(
                sec_id,
                {"id": sec_id, "name": sec_name, "types": []},
            )
            sections[sec_id]["types"].append({"id": t.get("id", ""), "name": t.get("name", "")})
        return {
            "id": ch_doc.get("chapter_id", ""),
            "name": ch_doc.get("chapter_name", ""),
            "sections": list(sections.values()),
        }
    raise ValueError("Unsupported chapter document shape")


def validate_taxonomy(taxonomy: dict) -> None:
    type_ids = set()
    for ch in taxonomy.get("chapters", []):
        ch_id = ch.get("id", "")
        if not CHAPTER_RE.match(ch_id):
            raise ValueError(f"Invalid chapter id: {ch_id}")
        if not ch.get("name"):
            raise ValueError(f"Missing chapter name: {ch_id}")

        section_ids = set()
        for sec in ch.get("sections", []):
            sec_id = sec.get("id", "")
            if not SECTION_RE.match(sec_id):
                raise ValueError(f"Invalid section id: {ch_id}/{sec_id}")
            if sec_id in section_ids:
                raise ValueError(f"Duplicate section id in chapter {ch_id}: {sec_id}")
            section_ids.add(sec_id)
            if not sec.get("name"):
                raise ValueError(f"Missing section name: {ch_id}/{sec_id}")

            for typ in sec.get("types", []):
                tid = typ.get("id", "")
                if not TYPE_RE.match(tid):
                    raise ValueError(f"Invalid type id: {ch_id}/{sec_id}/{tid}")
                if tid in type_ids:
                    raise ValueError(f"Duplicate type id: {tid}")
                type_ids.add(tid)
                if not typ.get("name"):
                    raise ValueError(f"Missing type name: {tid}")


def main() -> None:
    source_docs = load_chapter_docs()
    chapter_by_id: dict[str, dict] = {}
    for raw_doc in source_docs:
        chapter = normalize_obj(chapter_doc_to_chapter(raw_doc))
        # Last chapter wins for duplicate chapter_id.
        chapter_by_id[chapter["id"]] = chapter

    chapters = [chapter_by_id[k] for k in sorted(chapter_by_id.keys())]

    taxonomy = {
        "version": "2026-03-08",
        "id_format": {
            "chapter": "CHAPTER01..CHAPTER08",
            "section": "SECTION01..",
            "type": "TYPE001..TYPE120",
        },
        "normalization": {
            "rules": [
                "pH, Kp, Kc, COD, DO are half-width.",
                "Normalize arrows and equation symbols.",
                "Trim excessive whitespace.",
            ]
        },
        "chapters": chapters,
    }
    validate_taxonomy(taxonomy)
    OUT_PATH.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"chapters={len(chapters)} types={sum(len(s.get('types', [])) for c in chapters for s in c.get('sections', []))}")


if __name__ == "__main__":
    main()

