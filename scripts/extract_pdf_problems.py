import json
import os
import re
from dataclasses import dataclass

import fitz

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(ROOT_DIR, "data", "common", "2025_op_40_kagaku.pdf")
PDF_OUT_ROOT = os.path.join(ROOT_DIR, "data", "problems_pdf", "2025_op_40_kagaku")
RAW_OUT = os.path.join(ROOT_DIR, "data", "problems_raw.json")
FINAL_OUT = os.path.join(ROOT_DIR, "data", "problems.json")

QUESTION_LINE_RE = re.compile(r"^問\s*[0-9０-９]")


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    cleaned = []
    for line in lines:
        if not line:
            continue
        if re.match(r"^―[0-9０-９]+―$", line):
            continue
        if re.match(r"^（[0-9０-９]+―[0-9０-９]+）$", line):
            continue
        if line in {"化学", "学", "化"}:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def detect_markers(doc: fitz.Document):
    markers = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                line_text = line_text.strip()
                if not line_text:
                    continue
                if QUESTION_LINE_RE.match(line_text):
                    y0 = line["bbox"][1]
                    markers.append({
                        "page": page_index,
                        "y0": y0,
                        "text": line_text,
                    })
    markers.sort(key=lambda m: (m["page"], m["y0"]))
    return markers


@dataclass
class Segment:
    page: int
    y0: float
    y1: float


def build_segments(doc: fitz.Document, markers):
    segments_by_question = []
    for idx, marker in enumerate(markers):
        start_page = marker["page"]
        start_y = marker["y0"]
        if idx + 1 < len(markers):
            next_marker = markers[idx + 1]
            end_page = next_marker["page"]
            end_y = next_marker["y0"]
        else:
            next_marker = None
            end_page = None
            end_y = None

        segments = []
        if next_marker and end_page == start_page:
            segments.append(Segment(start_page, start_y, end_y))
        else:
            page = doc.load_page(start_page)
            segments.append(Segment(start_page, start_y, page.rect.height))
            if next_marker:
                for p in range(start_page + 1, end_page):
                    page = doc.load_page(p)
                    segments.append(Segment(p, 0, page.rect.height))
                segments.append(Segment(end_page, 0, end_y))
            else:
                for p in range(start_page + 1, doc.page_count):
                    page = doc.load_page(p)
                    segments.append(Segment(p, 0, page.rect.height))

        segments_by_question.append({
            "marker": marker,
            "segments": segments,
        })
    return segments_by_question


def extract_text(doc: fitz.Document, segments):
    chunks = []
    for seg in segments:
        page = doc.load_page(seg.page)
        rect = fitz.Rect(0, max(0, seg.y0 - 2), page.rect.width, min(page.rect.height, seg.y1))
        chunks.append(page.get_text("text", clip=rect))
    return normalize_text("\n".join(chunks))


def export_pdf(doc: fitz.Document, segments, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_doc = fitz.open()
    for seg in segments:
        page = doc.load_page(seg.page)
        rect = fitz.Rect(0, max(0, seg.y0 - 2), page.rect.width, min(page.rect.height, seg.y1))
        new_page = out_doc.new_page(width=rect.width, height=rect.height)
        new_page.show_pdf_page(new_page.rect, doc, seg.page, clip=rect)
    out_doc.save(out_path)
    out_doc.close()


MANUAL_CLASSIFY = {
    1: (["物質の構造", "無機"], ["結晶の種類", "イオン結晶"]),
    2: (["気体", "物理化学"], ["理想気体", "実在気体"]),
    3: (["気体", "溶液", "平衡"], ["溶解平衡", "ヘンリーの法則", "炭酸水"]),
    4: (["コロイド"], ["コロイド", "分散系"]),
    5: (["溶液", "物理化学"], ["蒸気圧降下", "浸透圧", "沸点上昇"]),
    6: (["化学反応", "光化学"], ["化学発光", "蛍光・りん光"]),
    7: (["電気化学"], ["電池", "酸化還元", "ニッケル・カドミウム電池"]),
    8: (["酸塩基", "溶液"], ["弱酸電離", "pH", "希釈"]),
    9: (["化学平衡", "工業化学", "気体"], ["ハーバー・ボッシュ法", "化学平衡", "反応条件"]),
    10: (["無機"], ["遷移元素", "錯体"]),
    11: (["無機"], ["ケイ酸塩", "ガラス"]),
    12: (["無機", "気体"], ["気体発生反応", "化学反応式"]),
    13: (["無機", "分析"], ["ヨウ素", "酸化還元", "製造"]),
    14: (["有機"], ["含酸素有機化合物", "反応"]),
    15: (["有機"], ["アクリル酸", "アニリン", "付加反応"]),
    16: (["有機", "天然物"], ["天然有機化合物", "構造"]),
    17: (["有機"], ["アセチレン", "付加反応"]),
    18: (["石油化学"], ["原油の分留", "留分"]),
    19: (["石油化学", "有機"], ["ナフサ改質", "芳香族", "ベンゼン誘導体"]),
    20: (["石油化学", "分析", "無機"], ["バナジウム", "錯体滴定", "酸化還元"]),
    21: (["石油化学"], ["原油の分留", "留分"]),
    22: (["石油化学", "有機"], ["ナフサ改質", "芳香族", "ベンゼン誘導体"]),
    23: (["石油化学", "分析", "無機"], ["バナジウム", "錯体滴定", "酸化還元"]),
}


def classify(text: str, index: int):
    if index in MANUAL_CLASSIFY:
        tags, concepts = MANUAL_CLASSIFY[index]
        return tags[:], concepts[:]
    tags = []
    concepts = []

    def add_tag(tag):
        if tag not in tags:
            tags.append(tag)

    def add_concept(concept):
        if concept not in concepts:
            concepts.append(concept)

    # broad tags
    if any(k in text for k in ["気体", "理想気体", "実在気体", "状態方程式"]):
        add_tag("気体")
        add_concept("気体")
    if any(k in text for k in ["平衡", "ルシャトリエ", "Kc", "Ka", "Kb", "溶解度積"]):
        add_tag("平衡")
    if any(k in text for k in ["pH", "中和", "滴定", "緩衝", "酸塩基"]):
        add_tag("酸塩基")
    if any(k in text for k in ["電池", "電解", "電極", "起電力", "酸化数", "酸化還元"]):
        add_tag("電気化学")
    if any(k in text for k in ["有機", "ベンゼン", "芳香族", "アセチレン", "アルコール", "エステル", "ナフサ", "原油", "アクリル", "高分子", "ポリマー"]):
        add_tag("有機")
    if any(k in text for k in ["遷移元素", "周期表", "ハロゲン", "アンモニア", "ケイ素", "ヨウ素", "硫酸", "硝酸"]):
        add_tag("無機")
    if any(k in text for k in ["沈殿", "炎色", "呈色", "定性", "定量", "分析"]):
        add_tag("分析")
    if any(k in text for k in ["エンタルピー", "ヘス", "結合エネルギー", "反応熱", "燃焼熱"]):
        add_tag("熱化学")
    if any(k in text for k in ["反応速度", "触媒"]):
        add_tag("反応速度")
    if any(k in text for k in ["濃度", "モル", "mol", "g", "L", "計算", "ppm"]):
        add_tag("化学計算")

    # concepts
    if "電池" in text:
        add_concept("電池")
    if "電解" in text:
        add_concept("電解")
    if "酸化還元" in text or "酸化数" in text:
        add_concept("酸化還元")
    if "pH" in text:
        add_concept("pH")
    if "滴定" in text:
        add_concept("滴定")
    if "緩衝" in text:
        add_concept("緩衝")
    if "平衡" in text:
        add_concept("化学平衡")
    if "ルシャトリエ" in text:
        add_concept("ルシャトリエの原理")
    if "溶解度積" in text:
        add_concept("溶解度積")
    if "沈殿" in text:
        add_concept("沈殿")
    if "炎色" in text:
        add_concept("炎色反応")
    if "状態方程式" in text:
        add_concept("気体の状態方程式")
    if "実在気体" in text:
        add_concept("実在気体")
    if "反応速度" in text or "速度" in text:
        add_concept("反応速度")
    if "触媒" in text:
        add_concept("触媒")
    if "有機" in text:
        add_concept("有機化学")
    if "ベンゼン" in text or "芳香族" in text:
        add_concept("芳香族")
    if "ポリマー" in text or "高分子" in text:
        add_concept("高分子")
    if "遷移元素" in text:
        add_concept("遷移元素")
    if "周期表" in text:
        add_concept("周期表")
    if "ハロゲン" in text:
        add_concept("ハロゲン")
    if "アンモニア" in text:
        add_concept("アンモニア")
    if "ヨウ素" in text:
        add_concept("ヨウ素")
    if "熱" in text or "エンタルピー" in text or "ヘス" in text:
        add_concept("熱化学")

    if not tags:
        tags.append("その他")
    if not concepts:
        concepts.append("その他")

    return tags, concepts


def main():
    doc = fitz.open(PDF_PATH)
    markers = detect_markers(doc)
    if not markers:
        raise SystemExit("No question markers found.")

    segments_by_question = build_segments(doc, markers)

    raw_output = []
    problems = []

    os.makedirs(PDF_OUT_ROOT, exist_ok=True)

    for idx, item in enumerate(segments_by_question, start=1):
        segments = item["segments"]
        marker = item["marker"]
        text = extract_text(doc, segments)

        lines = [line for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else f"Question {idx}"

        tags, concepts = classify(text, idx)

        pdf_filename = f"2025_op40_q{idx:02d}.pdf"
        pdf_rel = os.path.join("2025_op_40_kagaku", pdf_filename)
        pdf_out = os.path.join(PDF_OUT_ROOT, pdf_filename)
        export_pdf(doc, segments, pdf_out)

        raw_output.append({
            "index": idx,
            "marker": marker,
            "segments": [seg.__dict__ for seg in segments],
            "text": text,
        })

        problems.append({
            "id": f"2025_op40_q{idx:02d}",
            "title": title,
            "statement": text,
            "choices": [],
            "answer": "",
            "tags": tags,
            "concepts": concepts,
            "source": "2025_op_40_kagaku",
            "pdf": {"file": pdf_rel},
        })

    with open(RAW_OUT, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, ensure_ascii=False, indent=2)

    with open(FINAL_OUT, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)

    print(f"markers: {len(markers)}")
    print(f"problems: {len(problems)}")
    print(f"raw -> {RAW_OUT}")
    print(f"problems -> {FINAL_OUT}")
    print(f"pdfs -> {PDF_OUT_ROOT}")


if __name__ == "__main__":
    main()
