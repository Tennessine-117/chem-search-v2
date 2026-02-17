import hashlib
import html
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT_DIR, "data", "problems.json")
HOST = "127.0.0.1"
PORT = 8000
VECTOR_DIM = 4096
MAX_RESULTS = 10


def normalize_text(text):
    text = (text or "").lower()
    text = "".join(ch for ch in text if not ch.isspace())
    return text


def char_ngrams(text, n=2):
    if len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def hash_ngram(ngram):
    digest = hashlib.md5(ngram.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % VECTOR_DIM


def vectorize_text(text):
    normalized = normalize_text(text)
    grams = char_ngrams(normalized, 2)
    vec = {}
    for gram in grams:
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


PROBLEMS = load_problems()
PROBLEM_BY_ID = {item["id"]: item for item in PROBLEMS}
SEARCH_INDEX = []

for item in PROBLEMS:
    search_text = " ".join(
        [
            item.get("title", ""),
            item.get("statement", ""),
            " ".join(item.get("tags", [])),
            " ".join(item.get("concepts", [])),
        ]
    )
    SEARCH_INDEX.append((item["id"], vectorize_text(search_text)))


def search_problems(query):
    query_vec = vectorize_text(query)
    if not query_vec:
        return []

    scored = []
    for problem_id, vec in SEARCH_INDEX:
        score = cosine_similarity(query_vec, vec)
        if score > 0:
            problem = PROBLEM_BY_ID[problem_id]
            scored.append(
                {
                    "id": problem["id"],
                    "title": problem["title"],
                    "tags": problem.get("tags", []),
                    "score": round(float(score), 6),
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:MAX_RESULTS]


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def page_template(title, body_html):
    return f"""<!doctype html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem auto; max-width: 920px; padding: 0 1rem; line-height: 1.6; }}
    input[type=text] {{ width: 100%; padding: 0.7rem; font-size: 1rem; }}
    button {{ padding: 0.6rem 1rem; cursor: pointer; margin-top: 0.5rem; }}
    .result {{ border: 1px solid #ddd; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.7rem 0; }}
    .tags {{ color: #445; font-size: 0.9rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    a {{ color: #0b57d0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{ white-space: pre-wrap; }}
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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.handle_search_page()
            return

        if path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self.send_json({"query": query, "results": search_problems(query)})
            return

        if path.startswith("/problems/"):
            problem_id = path.removeprefix("/problems/")
            self.handle_problem_page(problem_id)
            return

        if path.startswith("/api/problems/"):
            problem_id = path.removeprefix("/api/problems/")
            problem = PROBLEM_BY_ID.get(problem_id)
            if not problem:
                self.not_found("Problem not found")
                return
            self.send_json(problem)
            return

        self.not_found()

    def log_message(self, fmt, *args):
        return

    def handle_search_page(self):
        body = """
<h1>化学問題 意味検索（V2 ミニマム）</h1>
<p class=\"muted\">自然言語で検索すると、類似度の高い問題を最大10件表示します。</p>
<input id=\"query\" type=\"text\" placeholder=\"例: 気体の状態方程式が必要になる問題を探して\" />
<button id=\"searchBtn\">検索</button>
<div id=\"resultInfo\" class=\"muted\"></div>
<div id=\"results\"></div>
<script>
const queryInput = document.getElementById('query');
const resultsEl = document.getElementById('results');
const infoEl = document.getElementById('resultInfo');

function renderResults(query, items) {
  infoEl.textContent = `クエリ: ${query} / ${items.length}件`;
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
      <span class="tags">tags: ${tags}</span><br>
      <span class="muted">score: ${item.score.toFixed(6)}</span>
    `;
    resultsEl.appendChild(div);
  }
}

async function runSearch() {
  const q = queryInput.value.trim();
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const data = await res.json();
  renderResults(data.query, data.results || []);
}

document.getElementById('searchBtn').addEventListener('click', runSearch);
queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runSearch();
});
</script>
"""
        self.send_html(page_template("化学問題検索", body))

    def handle_problem_page(self, problem_id):
        problem = PROBLEM_BY_ID.get(problem_id)
        if not problem:
            self.send_html(page_template("404", "<h1>404</h1><p>問題が見つかりません。</p>"), status=404)
            return

        choices = problem.get("choices") or []
        choices_html = "".join(f"<li>{html.escape(choice)}</li>" for choice in choices)
        if not choices_html:
            choices_html = "<li>選択肢なし</li>"

        body = f"""
<a href=\"/\">← 検索へ戻る</a>
<h1>{html.escape(problem['title'])}</h1>
<p><strong>ID:</strong> {html.escape(problem['id'])}</p>
<p><strong>tags:</strong> {html.escape(', '.join(problem.get('tags', [])))}</p>
<h2>問題文</h2>
<pre>{html.escape(problem.get('statement', ''))}</pre>
<h2>選択肢</h2>
<ol>
{choices_html}
</ol>
<button id=\"toggleAnswer\">答えを表示</button>
<div id=\"answerWrap\" style=\"display:none; margin-top: 0.8rem;\">
  <h2>答え</h2>
  <pre id=\"answerText\"></pre>
</div>
<script>
const btn = document.getElementById('toggleAnswer');
const wrap = document.getElementById('answerWrap');
const ans = document.getElementById('answerText');
let loaded = false;
let shown = false;

btn.addEventListener('click', async () => {{
  if (!loaded) {{
    const res = await fetch('/api/problems/{html.escape(problem_id)}');
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
