from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "data" / "taxonomy.json"


def uniq_keep_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def tokenize_name(name: str) -> list[str]:
    chunks = re.split(r"[・、，,（）()\s]+", name)
    tokens = [c.strip() for c in chunks if c.strip()]
    return uniq_keep_order(tokens)


def default_aliases(name: str) -> list[str]:
    aliases = [name]
    compact = re.sub(r"[・、，,\s]", "", name)
    if compact != name:
        aliases.append(compact)
    return uniq_keep_order(aliases)


def ensure_type_detail(t: dict, chapter_name: str, section_name: str) -> dict:
    type_name = t.get("name", "")
    tokens = tokenize_name(type_name)
    aliases = t.get("aliases") or default_aliases(type_name)
    summary = t.get("summary") or f"{chapter_name}／{section_name}で扱う「{type_name}」の典型問題タイプ。"

    t["aliases"] = aliases
    t["summary"] = summary
    t["classification"] = t.get("classification") or {
        "keywords": tokens[:8],
        "positive_indicators": [
            f"問題文に「{tok}」が含まれる" for tok in tokens[:3]
        ] or [f"問題文に「{type_name}」に関する語が含まれる"],
        "negative_indicators": [],
        "typical_expressions": [f"{type_name}を求めよ", f"{type_name}を判定せよ"],
        "input_features": ["問題文", "与えられた数値・条件"],
        "output_targets": [type_name],
    }
    t["concepts"] = t.get("concepts") or {
        "core_concepts": tokens[:5],
        "required_knowledge": [f"{type_name}の基本定義と標準的な解法手順"],
        "frequently_confused_with": [],
        "related_types": [],
    }
    t["solving"] = t.get("solving") or {
        "principal_formulas": [],
        "strategy": [
            "問題文から条件を整理する",
            "対応する基本式・法則を選ぶ",
            "計算後に単位・妥当性を確認する",
        ],
        "common_traps": ["条件の読み落とし", "単位の不一致", "係数・符号ミス"],
        "difficulty": "standard",
        "calculation_style": ["標準計算"],
        "required_math": ["四則演算"],
    }
    t["data_model"] = t.get("data_model") or {
        "given_values": ["問題文で与えられる値・条件"],
        "answer_forms": [type_name],
        "units": [],
        "constants": [],
    }
    return t


def main() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    updated = 0
    total = 0

    for ch in taxonomy.get("chapters", []):
        chapter_name = ch.get("name", "")
        chapter_id = ch.get("id", "")
        for sec in ch.get("sections", []):
            section_name = sec.get("name", "")
            section_id = sec.get("id", "")
            for t in sec.get("types", []):
                total += 1
                before = set(t.keys())
                t.setdefault("chapter_id", chapter_id)
                t.setdefault("section_id", section_id)
                t.setdefault("section_name", section_name)
                ensure_type_detail(t, chapter_name, section_name)
                if set(t.keys()) != before:
                    updated += 1

    taxonomy["version"] = "2026-03-08"
    TAXONOMY_PATH.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"types={total} enriched={updated}")


if __name__ == "__main__":
    main()

