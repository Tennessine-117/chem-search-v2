from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROBLEMS_PATH = DATA / "problems.json"
LINK_LOG_PATH = DATA / "answer_link_log.json"
TAXONOMY_PATH = DATA / "taxonomy.json"


# Curated mapping: linked explanation id -> taxonomy types.
# First type is treated as primary_type_id.
KAWAI_ANSWER_TYPE_MAP: dict[str, list[str]] = {
    "2025_kawai_a004": ["TYPE101"],  # 同素体
    "2025_kawai_a005": ["TYPE001"],  # 原子・電子配置
    "2025_kawai_a006": ["TYPE001"],  # イオン化エネルギー
    "2025_kawai_a007": ["TYPE103"],  # 物質の性質
    "2025_kawai_a008": ["TYPE032", "TYPE033"],  # 結晶構造・化学量
    "2025_kawai_a009": ["TYPE048"],  # 物質の溶解
    "2025_kawai_a010": ["TYPE048"],  # 固体の溶解度
    "2025_kawai_a011": ["TYPE092"],  # pH / 塩
    "2025_kawai_a012": ["TYPE027"],  # 酸化数
    "2025_kawai_a013": ["TYPE027"],  # 酸化還元の量
    "2025_kawai_a014": ["TYPE027"],  # イオン化傾向
    "2025_kawai_a015": ["TYPE069"],  # 酸化銀電池
    "2025_kawai_a016": ["TYPE014"],  # 化学量
    "2025_kawai_a017": ["TYPE045"],  # 状態図
    "2025_kawai_a018": ["TYPE008"],  # 気体の分子量
    "2025_kawai_a019": ["TYPE046"],  # 気体圧・水銀柱
    "2025_kawai_a020": ["TYPE043"],  # 混合気体
    "2025_kawai_a023": ["TYPE024"],  # 中和滴定
    "2025_kawai_a025": ["TYPE006"],  # 純物質/混合物
    "2025_kawai_a026": ["TYPE104"],  # 成分元素の検出
    "2025_kawai_a027": ["TYPE103"],  # 物質の性質・構造
    "2025_kawai_a028": ["TYPE068"],  # イオン結晶の結合
    "2025_kawai_a029": ["TYPE103"],  # 合金
    "2025_kawai_a030": ["TYPE045"],  # 気液平衡・蒸気圧
    "2025_kawai_a031": ["TYPE014"],  # 反応の量
    "2025_kawai_a032": ["TYPE045"],  # 気液平衡・蒸気圧
    "2025_kawai_a033": ["TYPE060", "TYPE061"],  # 浸透圧
    "2025_kawai_a034": ["TYPE048"],  # 固体溶解度
    "2025_kawai_a035": ["TYPE081"],  # 反応速度
    "2025_kawai_a036": ["TYPE085"],  # 化学平衡
    "2025_kawai_a037": ["TYPE088"],  # 弱酸
    "2025_kawai_a038": ["TYPE065"],  # 反応熱
    "2025_kawai_a039": ["TYPE101"],  # 無機反応
    "2025_kawai_a040": ["TYPE101"],  # 酸化物
    "2025_kawai_a041": ["TYPE102"],  # 工業的製法
    "2025_kawai_a044": ["TYPE014"],  # 化学量
    "2025_kawai_a045": ["TYPE090", "TYPE092"],  # 状態図/水のイオン積
    "2025_kawai_a046": ["TYPE031"],  # 結晶分類
    "2025_kawai_a047": ["TYPE055"],  # コロイド（溶液性質へ寄せる）
    "2025_kawai_a048": ["TYPE045"],  # 気液平衡
    "2025_kawai_a049": ["TYPE055"],  # 凝固点降下
    "2025_kawai_a050": ["TYPE037"],  # 最密構造
    "2025_kawai_a051": ["TYPE074"],  # 水溶液電気分解
    "2025_kawai_a053": ["TYPE082", "TYPE085"],  # 反応速度・平衡
    "2025_kawai_a054": ["TYPE088", "TYPE024"],  # 弱酸平衡・滴定
    "2025_kawai_a055": ["TYPE101"],  # リン
    "2025_kawai_a056": ["TYPE014"],  # 気体発生の量
    "2025_kawai_a057": ["TYPE101"],  # アルミニウム
    "2025_kawai_a058": ["TYPE006"],  # 化学式
    "2025_kawai_a059": ["TYPE101"],  # アルカリ土類
    "2025_kawai_a060": ["TYPE107"],  # 脂肪族の反応
    "2025_kawai_a061": ["TYPE107"],  # サリチル酸誘導体
    "2025_kawai_a062": ["TYPE107"],  # フェノール合成
    "2025_kawai_a063": ["TYPE105"],  # 異性体
    "2025_kawai_a064": ["TYPE102"],  # 鉄製錬
    "2025_kawai_a065": ["TYPE101"],  # 鉄イオン
    "2025_kawai_a066": ["TYPE014"],  # 化学量
    "2025_kawai_a067": ["TYPE031"],  # 酸化鉄構造
    "2025_kawai_a068": ["TYPE105"],  # 水素結合（構造分類へ寄せる）
    "2025_kawai_a069": ["TYPE052"],  # 気体溶解度
    "2025_kawai_a070": ["TYPE045"],  # 状態図
    "2025_kawai_a071": ["TYPE060"],  # 浸透圧
    "2025_kawai_a072": ["TYPE067"],  # エネルギー
    "2025_kawai_a073": ["TYPE094"],  # 溶解度積
    "2025_kawai_a074": ["TYPE073"],  # リチウムイオン電池
    "2025_kawai_a075": ["TYPE077"],  # イオン交換膜法
    "2025_kawai_a076": ["TYPE085", "TYPE082"],  # 平衡・速度
    "2025_kawai_a077": ["TYPE101"],  # 非金属元素
    "2025_kawai_a078": ["TYPE101"],  # 金属元素
    "2025_kawai_a079": ["TYPE040"],  # 気体の性質
    "2025_kawai_a080": ["TYPE097"],  # 陰イオン分離
    "2025_kawai_a081": ["TYPE107"],  # エタノール
    "2025_kawai_a082": ["TYPE105"],  # 異性体
    "2025_kawai_a083": ["TYPE109"],  # 高分子
    "2025_kawai_a084": ["TYPE107", "TYPE108"],  # 芳香族合成・収率
}


def build_type_index(taxonomy: dict) -> dict[str, dict[str, str]]:
    idx: dict[str, dict[str, str]] = {}
    for ch in taxonomy["chapters"]:
        ch_id = ch["id"]
        for sec in ch["sections"]:
            sec_id = sec["id"]
            for t in sec["types"]:
                idx[t["id"]] = {
                    "chapter_id": ch_id,
                    "section_id": sec_id,
                    "type_name": t["name"],
                }
    return idx


def uniq_keep_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def main() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    type_index = build_type_index(taxonomy)

    problems = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))
    link_log = json.loads(LINK_LOG_PATH.read_text(encoding="utf-8"))
    log_by_problem = {
        row["problem_id"]: row
        for row in link_log
        if row.get("source") == "2025_kawai"
    }

    updated = 0
    missing = []
    for item in problems:
        if item.get("source") != "2025_kawai":
            continue

        row = log_by_problem.get(item["id"], {})
        answer_id = row.get("answer_id", "")
        type_ids = uniq_keep_order(KAWAI_ANSWER_TYPE_MAP.get(answer_id, []))

        if not type_ids:
            missing.append((item["id"], answer_id))
            continue

        primary = type_ids[0]
        meta = type_index.get(primary)
        if not meta:
            missing.append((item["id"], answer_id))
            continue

        chapter_ids = []
        section_ids = []
        for type_id in type_ids:
            m = type_index.get(type_id)
            if not m:
                continue
            chapter_ids.append(m["chapter_id"])
            section_ids.append(m["section_id"])

        chapter_ids = uniq_keep_order(chapter_ids)
        section_ids = uniq_keep_order(section_ids)

        item["chapter_id"] = meta["chapter_id"]
        item["section_id"] = meta["section_id"]
        item["chapter_ids"] = chapter_ids
        item["section_ids"] = section_ids
        item["type_ids"] = type_ids
        item["primary_type_id"] = primary
        item["classification_basis"] = "manual_from_linked_explanation"
        updated += 1

    PROBLEMS_PATH.write_text(
        json.dumps(problems, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"updated: {updated}")
    print(f"missing: {len(missing)}")
    for pid, aid in missing[:20]:
        print(f"missing -> {pid} / {aid}")


if __name__ == "__main__":
    main()
