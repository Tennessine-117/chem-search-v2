+# chem-search-v2
+
+化学の問題を自然言語で意味検索する、ローカルWebアプリ（V2の最小構成）です。  
+追加ライブラリは不要で、**Python標準ライブラリのみ**で動作します。
+
+## 特徴
+
+- `data/problems.json` の問題データ（ダミー43問）を起動時に読み込み
+- 文字2-gram + hashing + cosine類似度で問題をベクトル検索
+- 検索UI（`/`）から自然文で検索し、類似度順に最大10件表示
+- **詳細検索フィルタ**（`source` / `tags` / `concepts`）対応
+  - `source` は完全一致
+  - `tags` / `concepts` はカンマ区切りで指定し、全条件一致（AND）
+- 問題詳細ページ（`/problems/<id>`）で問題文・選択肢を表示
+- 答えは初期非表示、ボタンで表示/非表示をトグル（`/api/problems/<id>`から取得）
+
+## API
+
+- `GET /api/search?q=...&source=...&tags=...&concepts=...`
+  - 最大10件
+  - 応答: `id`, `title`, `tags`, `source`, `score`
+- `GET /api/problems/<id>`（存在しない場合404）
+
+### 検索例
+
+- `GET /api/search?q=気体の状態方程式`
+- `GET /api/search?q=気体&source=dummy`
+- `GET /api/search?q=&source=dummy&tags=気体,計算`
+- `GET /api/search?q=平衡&concepts=ルシャトリエの原理`
+
+## 動作要件
+
+- Windows想定
+- Python 3.9+（標準ライブラリのみ使用）
+
+## 起動方法（Windows）
+
+PowerShell または コマンドプロンプトで以下を実行してください。
+
+```powershell
+cd <このリポジトリのパス>
+python app.py
+```
+
+起動後、ブラウザで以下へアクセスします。
+
+- <http://127.0.0.1:8000>
+
+## 操作方法
+
+1. `/`（検索ページ）を開く
+2. 自然言語クエリを入力（例：`気体の状態方程式が必要になる問題を探して`）
+3. 必要なら `source/tags/concepts` を入力して絞り込み
+4. 検索結果の `title + tags + source + score` を確認
+5. タイトルをクリックして `/problems/<id>` へ遷移
+6. 詳細ページで「答えを表示」を押すと答えを取得・表示
+7. もう一度押すと「答えを隠す」に切り替わる
+
+## データ
+
+- ファイル: `data/problems.json`
+- 問題スキーマ:
+  - `id`（URLに使える英数字+`_`）
+  - `title`
+  - `statement`
+  - `choices`（任意配列）
+  - `answer`（任意文字列）
+  - `tags`（配列）
+  - `concepts`（配列）
+  - `source`（現状 `"dummy"`）
+
+## 補足（将来拡張の想定）
+
+現時点はダミーデータを直接JSONで保持しています。将来的には、PDF問題セットのOCR/構造化、埋め込みモデルによる高精度検索、DB永続化などへ段階的に拡張できます。
