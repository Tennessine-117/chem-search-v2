import hashlib
import html
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT_DIR, "data", "problems.json")
PDF_ROOT = os.path.join(ROOT_DIR, "data", "problems_pdf")
HOST = "127.0.0.1"
PORT = 8000
VECTOR_DIM = 4096
MAX_RESULTS = 10


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


def load_problems():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    seen_ids = set()
    for item in items:
        required = ["id", "title", "statement", "tags", "concepts", "source"]
        missing = [k for k in required if k not in item]
        if missing:
            raise ValueError(f"Missing keys {missing} in problem {item}")
        if item["id"] in seen_ids:
            raise ValueError(f"Duplicate id: {item['id']}")
        seen_ids.add(item["id"])

    return items


def build_search_text(problem):
    return " ".join(
        [
            problem.get("title", ""),
            problem.get("statement", ""),
            " ".join(problem.get("tags", [])),
            " ".join(problem.get("concepts", [])),
            problem.get("source", ""),
        ]
    )


def build_search_index(problems):
    return [(item["id"], vectorize_text(build_search_text(item))) for item in problems]


PROBLEMS = load_problems()
PROBLEM_BY_ID = {item["id"]: item for item in PROBLEMS}
SEARCH_INDEX = build_search_index(PROBLEMS)


def match_filters(problem, source_filter, tags_filter, concepts_filter):
    if source_filter and problem.get("source", "") != source_filter:
        return False
    if tags_filter and not set(tags_filter).issubset(set(problem.get("tags", []))):
        return False
    if concepts_filter and not set(concepts_filter).issubset(set(problem.get("concepts", []))):
        return False
    return True


def search_problems(query, source_filter="", tags_filter=None, concepts_filter=None):
    tags_filter = tags_filter or []
    concepts_filter = concepts_filter or []

    query_vec = vectorize_text(query)
    use_vector = bool(query_vec)

    scored = []
    for problem_id, vec in SEARCH_INDEX:
        problem = PROBLEM_BY_ID[problem_id]
        if not match_filters(problem, source_filter, tags_filter, concepts_filter):
            continue

        score = cosine_similarity(query_vec, vec) if use_vector else 1.0
        if use_vector and score <= 0:
            continue

        scored.append(
            {
                "id": problem["id"],
                "title": problem["title"],
                "tags": problem.get("tags", []),
                "source": problem.get("source", ""),
                "score": round(float(score), 6),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:MAX_RESULTS]


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


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
    .row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.6rem; margin-top: 0.6rem; }}
    button {{ padding: 0.6rem 1rem; cursor: pointer; margin-top: 0.7rem; }}
    .result {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.7rem 0; }}
    .tags {{ color: #445; font-size: 0.9rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    a {{ color: #0b57d0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{ white-space: pre-wrap; }}
    @media (max-width: 760px) {{ .row {{ grid-template-columns: 1fr; }} }}
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

        if path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            source_filter = params.get("source", [""])[0].strip()
            tags_filter = parse_csv_values(params.get("tags", [""])[0])
            concepts_filter = parse_csv_values(params.get("concepts", [""])[0])
            self.send_json(
                {
                    "query": query,
                    "filters": {
                        "source": source_filter,
                        "tags": tags_filter,
                        "concepts": concepts_filter,
                    },
                    "results": search_problems(query, source_filter, tags_filter, concepts_filter),
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

    def log_message(self, fmt, *args):
        return

    def handle_search_page(self):
        body = """
<h1>化学問題 意味検索（V2 ミニマム）</h1>
<p class="muted">自然言語検索 + source/tags/conceptsで絞り込みできます（tags/conceptsはカンマ区切り）。</p>
<input id="query" type="text" placeholder="例: 気体の状態方程式が必要になる問題を探して" />
<div class="row">
  <input id="source" type="text" placeholder="source 例: dummy" />
  <input id="tags" type="text" placeholder="tags 例: 気体, 計算" />
  <input id="concepts" type="text" placeholder="concepts 例: 状態方程式" />
</div>
<button id="searchBtn">検索</button>
<div id="resultInfo" class="muted"></div>
<div id="results"></div>
<script>
const queryInput = document.getElementById('query');
const sourceInput = document.getElementById('source');
const tagsInput = document.getElementById('tags');
const conceptsInput = document.getElementById('concepts');
const resultsEl = document.getElementById('results');
const infoEl = document.getElementById('resultInfo');

function renderResults(query, filters, items) {
  const f = `source=${filters.source || '-'} / tags=${(filters.tags || []).join('|') || '-'} / concepts=${(filters.concepts || []).join('|') || '-'}`;
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
    div.innerHTML = `
      <a href="/problems/${encodeURIComponent(item.id)}"><strong>${item.title}</strong></a><br>
      <span class="tags">source: ${item.source || '-'} / tags: ${tags}</span><br>
      <span class="muted">score: ${Number(item.score).toFixed(6)}</span>
    `;
    resultsEl.appendChild(div);
  }
}

async function runSearch() {
  const params = new URLSearchParams();
  params.set('q', queryInput.value.trim());
  if (sourceInput.value.trim()) params.set('source', sourceInput.value.trim());
  if (tagsInput.value.trim()) params.set('tags', tagsInput.value.trim());
  if (conceptsInput.value.trim()) params.set('concepts', conceptsInput.value.trim());

  const res = await fetch(`/api/search?${params.toString()}`);
  const data = await res.json();
  renderResults(data.query, data.filters || {}, data.results || []);
}

document.getElementById('searchBtn').addEventListener('click', runSearch);
for (const input of [queryInput, sourceInput, tagsInput, conceptsInput]) {
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runSearch();
  });
}
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
<p><strong>tags:</strong> {html.escape(', '.join(problem.get('tags', [])))}</p>
<p><strong>concepts:</strong> {html.escape(', '.join(problem.get('concepts', [])))}</p>
<h2>問題文</h2>
<pre>{html.escape(problem.get('statement', ''))}</pre>
{pdf_section}
<h2>選択肢</h2>
<ol>{choices_html}</ol>
<button id="toggleAnswer">答えを表示</button>
<div id="answerWrap" style="display:none; margin-top: 0.8rem;">
  <h2>答え</h2>
  <pre id="answerText"></pre>
</div>
<script>
const btn = document.getElementById('toggleAnswer');
const wrap = document.getElementById('answerWrap');
const ans = document.getElementById('answerText');
let loaded = false;
let shown = false;

btn.addEventListener('click', async () => {{
  if (!loaded) {{
    const res = await fetch('/api/problems/{quote(problem_id, safe="")}');
    const data = await res.json();
    ans.textContent = data.answer || '答えデータなし';
    loaded = true;
  }}
  shown = !shown;
  wrap.style.display = shown ? 'block' : 'none';
  btn.textContent = shown ? '答えを隠す' : '答えを表示';
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
