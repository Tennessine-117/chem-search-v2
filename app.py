import hashlib
import html
import json
import math
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT_DIR, "data", "problems.json")
PDF_ROOT = os.path.join(ROOT_DIR, "data", "problems_pdf")
TAXONOMY_PATH = os.path.join(ROOT_DIR, "data", "taxonomy.json")
HOST = "127.0.0.1"
PORT = 8000
VECTOR_DIM = 4096
MAX_RESULTS = 10


def ensure_list_of_str(value):
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def uniq_keep_order(values):
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalize_text(text):
    return "".join(ch for ch in (text or "").lower() if not ch.isspace())


def char_ngrams(text, n=2):
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def hash_ngram(ngram):
    digest = hashlib.md5(ngram.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % VECTOR_DIM


def vectorize_text(text):
    vec = {}
    for gram in char_ngrams(normalize_text(text), 2):
        idx = hash_ngram(gram)
        vec[idx] = vec.get(idx, 0.0) + 1.0

    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm > 0:
        for idx in list(vec.keys()):
            vec[idx] /= norm
    return vec


def cosine_similarity(vec_a, vec_b):
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(value * vec_b.get(index, 0.0) for index, value in vec_a.items())


def parse_csv_values(raw_value):
    if not raw_value:
        return []
    return [v.strip() for v in raw_value.split(",") if v.strip()]


def load_taxonomy():
    if not os.path.exists(TAXONOMY_PATH):
        return {"chapters": []}, {}, {}, {}
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)

    chapter_names = {}
    section_names = {}
    type_meta = {}
    for ch in taxonomy.get("chapters", []):
        chapter_id = ch.get("id", "")
        chapter_names[chapter_id] = ch.get("name", "")
        for sec in ch.get("sections", []):
            section_id = sec.get("id", "")
            section_names[(chapter_id, section_id)] = sec.get("name", "")
            for typ in sec.get("types", []):
                type_id = typ.get("id", "")
                type_meta[type_id] = {
                    "name": typ.get("name", ""),
                    "chapter_id": chapter_id,
                    "section_id": section_id,
                }
    return taxonomy, chapter_names, section_names, type_meta


def load_problems():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    seen_ids = set()
    for item in items:
        required = ["id", "title", "statement", "tags", "source"]
        missing = [k for k in required if k not in item]
        if missing:
            raise ValueError(f"Missing keys {missing} in problem {item}")
        if item["id"] in seen_ids:
            raise ValueError(f"Duplicate id: {item['id']}")
        seen_ids.add(item["id"])
        item["narrow_tag"] = item.get("narrow_tag") or ""
        item["solution_outline"] = item.get("solution_outline") or ""
        item["solution_memo"] = item.get("solution_memo") or ""
        item["chapter_id"] = item.get("chapter_id") or ""
        item["section_id"] = item.get("section_id") or ""
        item["primary_type_id"] = item.get("primary_type_id") or ""
        item["type_ids"] = uniq_keep_order(ensure_list_of_str(item.get("type_ids")))
        item["chapter_ids"] = uniq_keep_order(ensure_list_of_str(item.get("chapter_ids")))
        item["section_ids"] = uniq_keep_order(ensure_list_of_str(item.get("section_ids")))
        if item["chapter_id"] and item["chapter_id"] not in item["chapter_ids"]:
            item["chapter_ids"].append(item["chapter_id"])
        if item["section_id"] and item["section_id"] not in item["section_ids"]:
            item["section_ids"].append(item["section_id"])
        item["classification_basis"] = item.get("classification_basis") or ""
        item["answer"] = item.get("answer") or ""
        item["answer_pdf"] = item.get("answer_pdf") or {}

    return items


def build_search_text(problem):
    solution = problem.get("solution_outline", "")
    solution_weighted = " ".join([solution] * 5).strip()
    memo = problem.get("solution_memo", "")
    memo_weighted = " ".join([memo] * 7).strip()
    tags_weighted = " ".join(problem.get("tags", []) * 2)
    return " ".join(
        [
            problem.get("title", ""),
            problem.get("statement", ""),
            tags_weighted,
            problem.get("narrow_tag", ""),
            solution_weighted,
            memo_weighted,
            problem.get("source", ""),
        ]
    )


def build_search_index(problems):
    return [(item["id"], vectorize_text(build_search_text(item))) for item in problems]


TAXONOMY, CHAPTER_NAME_BY_ID, SECTION_NAME_BY_KEY, TYPE_META_BY_ID = load_taxonomy()
DATA_LOCK = threading.Lock()
PROBLEMS = load_problems()
PROBLEM_BY_ID = {item["id"]: item for item in PROBLEMS}
SEARCH_INDEX = build_search_index(PROBLEMS)


def normalize_type_ids(problem):
    ids = ensure_list_of_str(problem.get("type_ids"))
    primary = (problem.get("primary_type_id") or "").strip()
    if primary and primary not in ids:
        ids.append(primary)
    return uniq_keep_order(ids)


def normalize_chapter_ids(problem):
    ids = ensure_list_of_str(problem.get("chapter_ids"))
    chapter_id = (problem.get("chapter_id") or "").strip()
    if chapter_id and chapter_id not in ids:
        ids.append(chapter_id)
    return uniq_keep_order(ids)


def normalize_section_ids(problem):
    ids = ensure_list_of_str(problem.get("section_ids"))
    section_id = (problem.get("section_id") or "").strip()
    if section_id and section_id not in ids:
        ids.append(section_id)
    return uniq_keep_order(ids)


def match_filters(
    problem,
    source_filter,
    tags_filter,
    chapter_filter="",
    section_filter="",
    type_filters=None,
    type_mode="any",
):
    type_filters = type_filters or []
    if source_filter and problem.get("source", "") != source_filter:
        return False
    if tags_filter and not set(tags_filter).issubset(set(problem.get("tags", []))):
        return False
    chapter_ids = set(normalize_chapter_ids(problem))
    section_ids = set(normalize_section_ids(problem))
    if chapter_filter and chapter_filter not in chapter_ids:
        return False
    if section_filter and section_filter not in section_ids:
        return False
    if type_filters:
        type_ids = set(normalize_type_ids(problem))
        selected = set(type_filters)
        if type_mode == "all":
            if not selected.issubset(type_ids):
                return False
        elif not (type_ids & selected):
            return False
    return True


def search_problems(
    query,
    source_filter="",
    tags_filter=None,
    chapter_filter="",
    section_filter="",
    type_filters=None,
    type_mode="any",
):
    tags_filter = tags_filter or []
    type_filters = type_filters or []

    query_vec = vectorize_text(query)
    use_vector = bool(query_vec)

    scored = []
    for problem_id, vec in SEARCH_INDEX:
        problem = PROBLEM_BY_ID[problem_id]
        if not match_filters(
            problem,
            source_filter,
            tags_filter,
            chapter_filter=chapter_filter,
            section_filter=section_filter,
            type_filters=type_filters,
            type_mode=type_mode,
        ):
            continue

        score = cosine_similarity(query_vec, vec) if use_vector else 1.0
        if use_vector and score <= 0:
            continue

        chapter_id = problem.get("chapter_id", "")
        section_id = problem.get("section_id", "")
        chapter_ids = normalize_chapter_ids(problem)
        section_ids = normalize_section_ids(problem)
        type_ids = normalize_type_ids(problem)
        section_name = SECTION_NAME_BY_KEY.get((chapter_id, section_id), "")
        type_names = [TYPE_META_BY_ID.get(tid, {}).get("name", "") for tid in type_ids]

        scored.append(
            {
                "id": problem["id"],
                "title": problem["title"],
                "tags": problem.get("tags", []),
                "narrow_tag": problem.get("narrow_tag", ""),
                "source": problem.get("source", ""),
                "chapter_id": chapter_id,
                "chapter_ids": chapter_ids,
                "chapter_name": CHAPTER_NAME_BY_ID.get(chapter_id, ""),
                "section_id": section_id,
                "section_ids": section_ids,
                "section_name": section_name,
                "type_ids": type_ids,
                "type_names": [x for x in type_names if x],
                "score": round(float(score), 6),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:MAX_RESULTS]


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def save_problems(items):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def rebuild_indexes():
    global PROBLEMS, PROBLEM_BY_ID, SEARCH_INDEX
    PROBLEMS = load_problems()
    PROBLEM_BY_ID = {item["id"]: item for item in PROBLEMS}
    SEARCH_INDEX = build_search_index(PROBLEMS)


def page_template(title, body_html):
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem auto; max-width: 980px; padding: 0 1rem; line-height: 1.6; }}
    input[type=text] {{ width: 100%; padding: 0.7rem; font-size: 1rem; }}
    select {{ width: 100%; padding: 0.7rem; font-size: 1rem; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.6rem; margin-top: 0.6rem; }}
    .row-2 {{ display: grid; grid-template-columns: 1fr 2fr; gap: 0.8rem; margin-top: 0.6rem; }}
    button {{ padding: 0.6rem 1rem; cursor: pointer; margin-top: 0.7rem; }}
    .result {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.7rem 0; }}
    .tags {{ color: #445; font-size: 0.9rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    .filter-box {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.6rem; max-height: 180px; overflow: auto; }}
    .filter-item {{ display: flex; gap: 0.5rem; align-items: center; padding: 0.1rem 0; }}
    .filter-item input {{ width: auto; }}
    a {{ color: #0b57d0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{ white-space: pre-wrap; }}
    @media (max-width: 760px) {{ .row {{ grid-template-columns: 1fr; }} .row-2 {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
{body_html}
</body>
</html>"""


class AppHandler(BaseHTTPRequestHandler):
    def send_html(self, text, status=200):
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, payload, status=200):
        encoded = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def not_found(self, message="Not Found"):
        self.send_json({"error": message}, status=404)

    def send_file(self, file_path, content_type="application/octet-stream"):
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            self.not_found("File not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.handle_search_page()
            return

        if path == "/api/filters":
            sources = {}
            tags = {}
            chapters = {}
            sections = {}
            types = {}
            for item in PROBLEMS:
                source = item.get("source", "")
                if source:
                    sources[source] = sources.get(source, 0) + 1
                for tag in item.get("tags", []) or []:
                    tags[tag] = tags.get(tag, 0) + 1
                chapter_ids = normalize_chapter_ids(item)
                for chapter_id in chapter_ids:
                    chapters[chapter_id] = chapters.get(chapter_id, 0) + 1
                # Prefer type-based chapter/section pairs for accurate cross-chapter tagging.
                type_pairs = []
                for type_id in normalize_type_ids(item):
                    meta = TYPE_META_BY_ID.get(type_id) or {}
                    ch = meta.get("chapter_id", "")
                    sec = meta.get("section_id", "")
                    if ch and sec:
                        type_pairs.append((ch, sec))
                if type_pairs:
                    for key in uniq_keep_order(type_pairs):
                        sections[key] = sections.get(key, 0) + 1
                else:
                    section_ids = normalize_section_ids(item)
                    for section_id in section_ids:
                        for chapter_id in chapter_ids:
                            key = (chapter_id, section_id)
                            sections[key] = sections.get(key, 0) + 1
                for type_id in normalize_type_ids(item):
                    types[type_id] = types.get(type_id, 0) + 1
            self.send_json(
                {
                    "sources": [
                        {"value": key, "count": sources[key]}
                        for key in sorted(sources.keys())
                    ],
                    "tags": [
                        {"value": key, "count": tags[key]}
                        for key in sorted(tags.keys())
                    ],
                    "chapters": [
                        {
                            "id": key,
                            "name": CHAPTER_NAME_BY_ID.get(key, key),
                            "count": chapters[key],
                        }
                        for key in sorted(chapters.keys())
                    ],
                    "sections": [
                        {
                            "chapter_id": ch,
                            "section_id": sec,
                            "name": SECTION_NAME_BY_KEY.get((ch, sec), sec),
                            "count": sections[(ch, sec)],
                        }
                        for (ch, sec) in sorted(sections.keys())
                    ],
                    "types": [
                        {
                            "id": tid,
                            "name": TYPE_META_BY_ID.get(tid, {}).get("name", tid),
                            "chapter_id": TYPE_META_BY_ID.get(tid, {}).get("chapter_id", ""),
                            "section_id": TYPE_META_BY_ID.get(tid, {}).get("section_id", ""),
                            "count": types[tid],
                        }
                        for tid in sorted(types.keys())
                    ],
                }
            )
            return

        if path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            source_filter = params.get("source", [""])[0].strip()
            tags_filter = parse_csv_values(params.get("tags", [""])[0])
            chapter_filter = params.get("chapter", [""])[0].strip()
            section_filter = params.get("section", [""])[0].strip()
            type_filters = parse_csv_values(params.get("types", [""])[0])
            type_mode = params.get("type_mode", ["any"])[0].strip().lower()
            if type_mode not in {"any", "all"}:
                type_mode = "any"
            self.send_json(
                {
                    "query": query,
                    "filters": {
                        "source": source_filter,
                        "tags": tags_filter,
                        "chapter": chapter_filter,
                        "section": section_filter,
                        "types": type_filters,
                        "type_mode": type_mode,
                    },
                    "results": search_problems(
                        query,
                        source_filter,
                        tags_filter,
                        chapter_filter=chapter_filter,
                        section_filter=section_filter,
                        type_filters=type_filters,
                        type_mode=type_mode,
                    ),
                }
            )
            return

        if path.startswith("/problems/"):
            self.handle_problem_page(path.removeprefix("/problems/"))
            return

        if path.startswith("/api/problems/"):
            problem_id = path.removeprefix("/api/problems/")
            problem = PROBLEM_BY_ID.get(problem_id)
            if not problem:
                self.not_found("Problem not found")
                return
            self.send_json(problem)
            return

        if path.startswith("/pdf/"):
            rel = path.removeprefix("/pdf/")
            safe_rel = os.path.normpath(rel).lstrip("/\\")
            file_path = os.path.join(PDF_ROOT, safe_rel)
            if not os.path.abspath(file_path).startswith(os.path.abspath(PDF_ROOT) + os.sep):
                self.not_found("Invalid path")
                return
            self.send_file(file_path, content_type="application/pdf")
            return

        self.not_found()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/source/rename":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, status=400)
                return

            old_source = (payload.get("old") or "").strip()
            new_source = (payload.get("new") or "").strip()
            if not old_source or not new_source:
                self.send_json({"error": "old/new required"}, status=400)
                return

            with DATA_LOCK:
                updated = 0
                for item in PROBLEMS:
                    if item.get("source", "") == old_source:
                        item["source"] = new_source
                        updated += 1
                if updated == 0:
                    self.send_json({"error": "No items updated"}, status=404)
                    return
                save_problems(PROBLEMS)
                rebuild_indexes()

            self.send_json({"updated": updated, "old": old_source, "new": new_source})
            return

        if path == "/api/source/set":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_json({"error": "Invalid JSON"}, status=400)
                return

            problem_id = (payload.get("id") or "").strip()
            new_source = (payload.get("source") or "").strip()
            if not problem_id or not new_source:
                self.send_json({"error": "id/source required"}, status=400)
                return

            with DATA_LOCK:
                problem = PROBLEM_BY_ID.get(problem_id)
                if not problem:
                    self.send_json({"error": "Problem not found"}, status=404)
                    return
                problem["source"] = new_source
                save_problems(PROBLEMS)
                rebuild_indexes()

            self.send_json({"id": problem_id, "source": new_source})
            return

        self.not_found()

    def log_message(self, fmt, *args):
        return

    def handle_search_page(self):
        body = """
<h1>化学問題 意味検索（V2 ミニマム）</h1>
<p class="muted">自然言語検索 + source/tags + chapter/section/type で絞り込みできます（選択式）。</p>
<input id="query" type="text" placeholder="例: 気体の状態方程式が必要になる問題を探して" />
<div class="row-2">
  <div>
    <label for="source">source</label>
    <select id="source">
      <option value="">すべて</option>
    </select>
  </div>
  <div>
    <div style="display:flex; align-items:center; justify-content:space-between;">
      <label>tags</label>
      <button id="clearTags" type="button">全解除</button>
    </div>
    <div id="tagsBox" class="filter-box"></div>
  </div>
</div>
<div class="row">
  <div>
    <label for="chapter">chapter</label>
    <select id="chapter">
      <option value="">すべて</option>
    </select>
  </div>
  <div>
    <label for="section">section</label>
    <select id="section">
      <option value="">すべて</option>
    </select>
  </div>
  <div>
    <label for="typeMode">type一致</label>
    <select id="typeMode">
      <option value="any">OR（いずれか）</option>
      <option value="all">AND（すべて）</option>
    </select>
  </div>
</div>
<div style="margin-top:0.6rem;">
  <div style="display:flex; align-items:center; justify-content:space-between;">
    <label>types（複数選択）</label>
    <button id="clearTypes" type="button">全解除</button>
  </div>
  <div id="typesBox" class="filter-box"></div>
</div>
<button id="searchBtn">検索</button>
<div id="resultInfo" class="muted"></div>
<div id="results"></div>
<hr>
<h2>Source名の一括変更（管理）</h2>
<div class="row">
  <input id="oldSource" type="text" placeholder="旧 source" />
  <input id="newSource" type="text" placeholder="新 source" />
  <button id="renameSourceBtn">一括変更</button>
</div>
<div id="renameInfo" class="muted"></div>
<script>
const queryInput = document.getElementById('query');
const sourceInput = document.getElementById('source');
const tagsBox = document.getElementById('tagsBox');
const chapterInput = document.getElementById('chapter');
const sectionInput = document.getElementById('section');
const typeModeInput = document.getElementById('typeMode');
const typesBox = document.getElementById('typesBox');
const resultsEl = document.getElementById('results');
const infoEl = document.getElementById('resultInfo');
const oldSourceInput = document.getElementById('oldSource');
const newSourceInput = document.getElementById('newSource');
const renameInfo = document.getElementById('renameInfo');
const clearTagsBtn = document.getElementById('clearTags');
const clearTypesBtn = document.getElementById('clearTypes');
let filterData = {sources: [], tags: [], chapters: [], sections: [], types: []};

function getSelectedTags() {
  const tags = [];
  for (const cb of tagsBox.querySelectorAll('input[type="checkbox"]')) {
    if (cb.checked) tags.push(cb.value);
  }
  return tags;
}

function getSelectedTypes() {
  const types = [];
  for (const cb of typesBox.querySelectorAll('input[type="checkbox"]')) {
    if (cb.checked) types.push(cb.value);
  }
  return types;
}

function syncSectionOptions() {
  const selectedChapter = chapterInput.value;
  sectionInput.innerHTML = '<option value="">すべて</option>';
  for (const sec of filterData.sections || []) {
    if (!selectedChapter || sec.chapter_id === selectedChapter) {
      const opt = document.createElement('option');
      opt.value = sec.section_id;
      opt.textContent = `${sec.name} (${sec.count})`;
      sectionInput.appendChild(opt);
    }
  }
}

function syncTypeVisibility() {
  const selectedChapter = chapterInput.value;
  const selectedSection = sectionInput.value;
  for (const label of typesBox.querySelectorAll('label.filter-item')) {
    const chapterId = label.dataset.chapterId || '';
    const sectionId = label.dataset.sectionId || '';
    const okChapter = !selectedChapter || chapterId === selectedChapter;
    const okSection = !selectedSection || sectionId === selectedSection;
    label.style.display = (okChapter && okSection) ? '' : 'none';
  }
}

function renderFilters(filters) {
  filterData = filters || filterData;
  for (const item of filters.sources || []) {
    const opt = document.createElement('option');
    opt.value = item.value;
    opt.textContent = `${item.value} (${item.count})`;
    sourceInput.appendChild(opt);
  }

  tagsBox.innerHTML = '';
  for (const item of filters.tags || []) {
    const label = document.createElement('label');
    label.className = 'filter-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = item.value;
    const text = document.createElement('span');
    text.textContent = `${item.value} (${item.count})`;
    label.appendChild(cb);
    label.appendChild(text);
    tagsBox.appendChild(label);
  }

  for (const item of filters.chapters || []) {
    const opt = document.createElement('option');
    opt.value = item.id;
    opt.textContent = `${item.name} (${item.count})`;
    chapterInput.appendChild(opt);
  }

  syncSectionOptions();

  typesBox.innerHTML = '';
  for (const item of filters.types || []) {
    const label = document.createElement('label');
    label.className = 'filter-item';
    label.dataset.chapterId = item.chapter_id || '';
    label.dataset.sectionId = item.section_id || '';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = item.id;
    const text = document.createElement('span');
    text.textContent = `${item.id} ${item.name} (${item.count})`;
    label.appendChild(cb);
    label.appendChild(text);
    typesBox.appendChild(label);
  }
  syncTypeVisibility();
}

function renderResults(query, filters, items) {
  const f = `source=${filters.source || '-'} / tags=${(filters.tags || []).join('|') || '-'} / chapter=${filters.chapter || '-'} / section=${filters.section || '-'} / types(${filters.type_mode || 'any'})=${(filters.types || []).join('|') || '-'}`;
  infoEl.textContent = `クエリ: ${query || '(空)'} / ${items.length}件 / ${f}`;
  resultsEl.innerHTML = '';
  if (!items.length) {
    resultsEl.innerHTML = '<p>該当する問題が見つかりませんでした。</p>';
    return;
  }
  for (const item of items) {
    const div = document.createElement('div');
    div.className = 'result';
    const tags = (item.tags || []).join(', ');
    const narrow = item.narrow_tag ? ` / narrow: ${item.narrow_tag}` : '';
    const chapter = item.chapter_name || item.chapter_id || '-';
    const section = item.section_name || item.section_id || '-';
    const types = (item.type_ids || []).join(', ') || '-';
    div.innerHTML = `
      <a href="/problems/${encodeURIComponent(item.id)}"><strong>${item.title}</strong></a><br>
      <span class="tags">source: ${item.source || '-'} / tags: ${tags}${narrow}</span><br>
      <span class="muted">chapter: ${chapter} / section: ${section} / types: ${types}</span><br>
      <span class="muted">score: ${Number(item.score).toFixed(6)}</span>
    `;
    resultsEl.appendChild(div);
  }
}

async function runSearch() {
  const params = new URLSearchParams();
  params.set('q', queryInput.value.trim());
  if (sourceInput.value) params.set('source', sourceInput.value);
  if (chapterInput.value) params.set('chapter', chapterInput.value);
  if (sectionInput.value) params.set('section', sectionInput.value);
  if (typeModeInput.value) params.set('type_mode', typeModeInput.value);
  const tags = getSelectedTags();
  if (tags.length) params.set('tags', tags.join(','));
  const types = getSelectedTypes();
  if (types.length) params.set('types', types.join(','));

  const res = await fetch(`/api/search?${params.toString()}`);
  const data = await res.json();
  renderResults(data.query, data.filters || {}, data.results || []);
}

async function loadFilters() {
  const res = await fetch('/api/filters');
  const data = await res.json();
  renderFilters(data);
}

async function renameSource() {
  const oldVal = oldSourceInput.value.trim();
  const newVal = newSourceInput.value.trim();
  if (!oldVal || !newVal) {
    renameInfo.textContent = '旧/新sourceを入力してください。';
    return;
  }
  const res = await fetch('/api/source/rename', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({old: oldVal, new: newVal})
  });
  const data = await res.json();
  if (!res.ok) {
    renameInfo.textContent = data.error || '変更に失敗しました。';
    return;
  }
  renameInfo.textContent = `更新件数: ${data.updated}`;
}

document.getElementById('searchBtn').addEventListener('click', runSearch);
document.getElementById('renameSourceBtn').addEventListener('click', renameSource);
clearTagsBtn.addEventListener('click', () => {
  for (const cb of tagsBox.querySelectorAll('input[type="checkbox"]')) {
    cb.checked = false;
  }
});
clearTypesBtn.addEventListener('click', () => {
  for (const cb of typesBox.querySelectorAll('input[type="checkbox"]')) {
    cb.checked = false;
  }
});
chapterInput.addEventListener('change', () => {
  syncSectionOptions();
  syncTypeVisibility();
});
sectionInput.addEventListener('change', syncTypeVisibility);
for (const input of [queryInput, sourceInput, chapterInput, sectionInput]) {
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runSearch();
  });
}
loadFilters();
</script>
"""
        self.send_html(page_template("化学問題検索", body))

    def handle_problem_page(self, problem_id):
        problem = PROBLEM_BY_ID.get(problem_id)
        if not problem:
            self.send_html(page_template("404", "<h1>404</h1><p>問題が見つかりません。</p>"), status=404)
            return

        choices = problem.get("choices") or []
        choices_html = "".join(f"<li>{html.escape(choice)}</li>" for choice in choices) or "<li>選択肢なし</li>"

        pdf_section = ""
        pdf_info = problem.get("pdf") or {}
        pdf_file = pdf_info.get("file")
        if pdf_file:
            rel = os.path.relpath(os.path.join(ROOT_DIR, "data", "problems_pdf", pdf_file), PDF_ROOT)
            rel = rel.replace("\\", "/")
            pdf_url = f"/pdf/{rel}"
            pdf_section = f"""
<h2>問題PDF</h2>
<p><a href="{pdf_url}" target="_blank" rel="noopener">PDFを別タブで開く</a></p>
<iframe src="{pdf_url}" width="100%" height="720" style="border: 1px solid #ddd; border-radius: 6px;"></iframe>
"""

        body = f"""
<a href="/">← 検索へ戻る</a>
<h1>{html.escape(problem['title'])}</h1>
<p><strong>ID:</strong> {html.escape(problem['id'])}</p>
<p><strong>source:</strong> {html.escape(problem.get('source', ''))}</p>
<div class="row" style="margin-bottom: 0.6rem;">
  <input id="sourceEdit" type="text" placeholder="sourceを変更" />
  <button id="sourceEditBtn">保存</button>
</div>
<div id="sourceEditInfo" class="muted"></div>
<p><strong>tags:</strong> {html.escape(', '.join(problem.get('tags', [])))}</p>
<p><strong>narrow tag:</strong> {html.escape(problem.get('narrow_tag', ''))}</p>
{pdf_section}
<h2>選択肢</h2>
<ol>{choices_html}</ol>
<button id="toggleAnswer">答えを表示</button>
<div id="answerWrap" style="display:none; margin-top: 0.8rem;">
  <h2>答え</h2>
  <div id="answerContent"></div>
</div>
<script>
const btn = document.getElementById('toggleAnswer');
const wrap = document.getElementById('answerWrap');
const answerContent = document.getElementById('answerContent');
const sourceEdit = document.getElementById('sourceEdit');
const sourceEditBtn = document.getElementById('sourceEditBtn');
const sourceEditInfo = document.getElementById('sourceEditInfo');
let loaded = false;
let shown = false;

btn.addEventListener('click', async () => {{
  if (!loaded) {{
    const res = await fetch('/api/problems/{quote(problem_id, safe="")}');
    const data = await res.json();
    answerContent.innerHTML = '';
    const answerPdf = (data.answer_pdf && data.answer_pdf.file) ? String(data.answer_pdf.file) : '';
    if (answerPdf) {{
      const normalized = answerPdf.replace(/\\\\/g, '/');
      const pdfUrl = `/pdf/${{normalized}}`;
      const p = document.createElement('p');
      const a = document.createElement('a');
      a.href = pdfUrl;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = '解答解説PDFを別タブで開く';
      p.appendChild(a);
      answerContent.appendChild(p);

      const iframe = document.createElement('iframe');
      iframe.src = pdfUrl;
      iframe.width = '100%';
      iframe.height = '720';
      iframe.style.border = '1px solid #ddd';
      iframe.style.borderRadius = '6px';
      answerContent.appendChild(iframe);
    }} else {{
      const pre = document.createElement('pre');
      pre.textContent = data.answer || '答えデータなし';
      answerContent.appendChild(pre);
    }}
    loaded = true;
  }}
  shown = !shown;
  wrap.style.display = shown ? 'block' : 'none';
  btn.textContent = shown ? '答えを隠す' : '答えを表示';
}});

sourceEditBtn.addEventListener('click', async () => {{
  const val = sourceEdit.value.trim();
  if (!val) {{
    sourceEditInfo.textContent = 'sourceを入力してください。';
    return;
  }}
  const res = await fetch('/api/source/set', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id: '{problem_id}', source: val}})
  }});
  const data = await res.json();
  if (!res.ok) {{
    sourceEditInfo.textContent = data.error || '更新に失敗しました。';
    return;
  }}
  sourceEditInfo.textContent = '更新しました。リロードしてください。';
}});
</script>
"""
        self.send_html(page_template(problem["title"], body))


def run_server():
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Serving on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
