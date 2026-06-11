# INIAD-AIO

## AIO v0.2 Current Status

AIO v0.2 is a proof-of-concept assistant for searching INIAD course information,
MOOCs page locations, assignments, and limited page-body text. It is not yet a
full slide/PDF RAG system.

### What Works

* FastAPI backend and simple frontend UI.
* PostgreSQL-backed import of courses, lectures, pages, materials, and tasks.
* Meilisearch indexing and `/api/search` for course, lecture, page, material, and task search.
* `/api/ask` with search-backed Gemini answers and timeout fallback.
* Task extraction for COT101 / CS概論 I, including many assignment pages.
* MOOCs metadata probing for COT101 with a persistent Playwright profile.
* MOOCs page-body extraction for normal HTML pages and quiz/task-like pages.
* Content RAG works only where the page DOM contains real text.
* Login-page detection prevents `/signin` pages from being saved as `extracted_text`.

### What Does Not Work Yet

* Google Slides iframe body text is not extracted.
* PDF extraction is not implemented.
* OCR is not implemented.
* Embeddings/vector search are not implemented.
* Pages whose main content is only a Google Slides iframe currently store only
  the surrounding page text, such as the title and navigation.
* Headless Playwright must not be used for MOOCs authenticated retrieval. Use a
  dedicated headed profile via `MOOCS_USER_DATA_DIR`.

### Current Scope

The current system should be described as:

* lecture-location search
* assignment search
* limited content RAG for HTML text that exists directly in the MOOCs page DOM

It should not be described as full lecture-slide RAG yet, because Slides iframe
content is still outside the extracted text.

### Recommended v0.2 Wording

> AIO v0.2 supports MOOCs metadata import, lecture/page location search,
> assignment search, and partial HTML-body RAG. It does not yet extract text from
> Google Slides iframes, PDFs, or images.

INIAD生向けAIアシスタントプロジェクト。

講義資料・課題・大学情報をデータベース化し、自然言語で検索・質問できるシステムの開発を目指しています。

---

## 現在の状況

現在はPoC（Proof of Concept）段階です。

実装済み機能

* FastAPI バックエンド
* SQLite データベース
* Gemini API 連携
* 自然言語による検索
* Web UI
* 回答生成
* 参照データ（Sources）表示

現在の処理フロー

```text
質問
↓
SQLite検索
↓
Gemini回答生成
↓
Web UI表示
```

---

## Markdown形式データ管理について

INIAD-AIOでは、講義ノートや課題情報をMarkdown形式で管理しています。

データは以下のディレクトリに保存します。

```text
data/

├─ lectures/
├─ tasks/
├─ obsidian_testdata/
└─ templates/
```

lectures, tasks は本番データ格納用、
obsidian_testdata は開発・検証用データ格納用です。

### lectures

講義ノートを保存します。

例:

```text
data/lectures/情報連携学概論Ⅰ/
```

### tasks

課題情報を保存します。

例:

```text
data/tasks/情報連携基礎実習Ⅰ/
```

### obsidian_testdata

開発・検証用のMarkdownデータを保存します。

PoCや動作確認、検索テストに使用するデータを配置します。

例:

```text
data/obsidian_testdata/
```

### templates

新規データ作成時のテンプレートを保存します。

* lecture_template.md
* task_template.md

## データ入力ルール

講義ノートは lecture_template.md を利用してください。

課題情報は task_template.md を利用してください。

現在使用するプロパティ:

講義

* type
* course
* date

課題

* type
* course
* deadline

プロパティ名は統一のため変更しないでください。

## プロジェクトへの貢献

講義ノートや課題情報の追加も重要な貢献です。

プログラミング経験がなくても、Markdown形式でデータを追加することでプロジェクトに参加できます。

---

## ディレクトリ構成

```text
INIAD-AIO/

├─ backend/
│  ├─ main.py
│  ├─ ai_module.py
│  ├─ database.py
│  ├─ search_backend.py
│  └─ aio.db

├─ frontend/
│  ├─ index.html
│  └─ style.css

├─ data/
│  ├─ lectures/
│  ├─ tasks/
│  ├─ obsidian_testdata/
│  └─ templates/
│     ├─ lecture_template.md
│     └─ task_template.md

└─ README.md
```


---

## セットアップ

### 仮想環境有効化

Windows

```powershell
.\.venv\Scripts\activate
```

### サーバー起動

```powershell
cd backend
uvicorn main:app --reload
```

### アクセス

```text
http://127.0.0.1:8000
```

---

## 現在の開発段階

### v0.05

実装済み

* FastAPI
* SQLite
* Gemini API
* Frontend UI
* Sources表示
* Enter送信
* Loading表示

### v0.1

予定

* Obsidian講義ノート投入
* 実データによる検索
* デモ版完成

### v0.2

予定

* MOOCs連携
* データ投入自動化

### v0.3

予定

* Embedding導入
* ベクトル検索

### v0.4

予定

* RAG基盤構築

### v1.0

予定

* プロダクト化
* UI改善
* 安定運用

---

## 現在の課題

* Obsidianデータ投入
* データ量不足
* MOOCs連携
* Embedding設計
* メンバー募集

---

## ライセンス

開発中

```
```

---

## MOOCs 取得PoC

v0.2 の MOOCs 取得PoCとして、ログイン済み `storage_state` を使って `https://moocs.iniad.org/courses` の講義一覧をDOMから抽出します。INIAD++調査および `MOOCs取得調査.md` では MOOCs 内部APIを確認できていないため、このPoCはDOM依存です。今後 `MoocsSourceProvider` に発展させる前提で、Google Slides iframe / Viewer DOM を扱うことを想定しています。

### 初回セットアップ

```powershell
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
python -m playwright install chromium
New-Item -ItemType Directory -Force data\probe
```

### 初回ログインと storage_state 作成

ブラウザを開いて MOOCs にログインし、ログイン状態を `data/probe/moocs_storage_state.json` に保存します。

```powershell
python -m playwright codegen --save-storage=data/probe/moocs_storage_state.json https://moocs.iniad.org/courses
```

ログイン後、表示されたブラウザを閉じると storage_state が保存されます。`storage_state` には認証情報が含まれるため、Gitにはコミットしないでください。

### 講義一覧の取得

```powershell
python backend\moocs_probe.py
```

出力先:

```text
data/probe/moocs_courses.json
```

取得件数が0件の場合はエラーとして終了します。selector は暫定で、失敗時にはページタイトル、URL、リンク候補、Google Slides / Viewer iframe の検出状況をログに出します。
### MOOCs details metadata probe

`--details` visits course top pages, lesson group pages, and lesson pages, then stores Google Slides iframe metadata in `data/probe/moocs_course_details.json`.

Use persistent profile login for the most stable MOOCs session. The profile can hold login cookies, so keep `data/probe/moocs_profile/` out of Git.

```powershell
python backend\moocs_probe.py --details --course-code COT101 --user-data-dir data\probe\moocs_profile --headed --timeout-ms 30000 --verbose
```

On first run, complete the MOOCs login in the opened browser and press Enter in the terminal. Later runs can reuse the same profile:

```powershell
python backend\moocs_probe.py --details --course-code COT101 --user-data-dir data\probe\moocs_profile --timeout-ms 30000
curl.exe -X POST http://localhost:8000/api/import-moocs-details
```

`/api/import-moocs-details` imports metadata only: courses, lectures, materials
that can be linked to existing pages, and tasks. It intentionally does not run
`/api/import-pages`.

Limits:

* `--details-limit N`: max courses to visit.
* `--lesson-limit N`: max lesson groups per course.
* `--page-limit N`: max lesson pages per lesson group.

The details output is metadata-only. It does not store raw body text or `text_preview`.

### Refresh MOOCs storage_state and content RAG for COT101

MOOCs content retrieval must use headed Chromium for now. Do not run the same
MOOCs profile with `headless=true`; a headless run can send the session back to
`/signin` and may invalidate the profile. Use a dedicated profile directory for
content import.

```powershell
python backend\moocs_probe.py --check-url https://moocs.iniad.org/courses/2026/COT101/01-1/01 --user-data-dir data\probe\moocs_profile_content --headed --timeout-ms 30000 --verbose
```

Expected result:

```json
{
  "ok": true,
  "redirected_to_signin": false
}
```

For local content import, run the API from the Windows virtualenv with the headed
persistent profile instead of the Docker API. `MOOCS_USER_DATA_DIR` should point
to the dedicated content profile. `MOOCS_PLAYWRIGHT_HEADLESS` is ignored by the
fallback because MOOCs content retrieval is headed-only.

```powershell
$env:DATABASE_URL = "postgresql://aio_user:aio_password@localhost:5432/aio_db"
$env:MEILI_URL = "http://localhost:7700"
$env:MEILI_MASTER_KEY = "dev-master-key"
$env:MEILI_INDEX = "search_documents"
$env:MOOCS_USER_DATA_DIR = "data\probe\moocs_profile_content"
.\.venv\Scripts\uvicorn.exe main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Then refresh/import only the COT101 page metadata and body text. Keep the order
`import-pages -> reindex-search -> ask` unchanged:

```powershell
python backend\moocs_probe.py --details --course-code COT101 --user-data-dir data\probe\moocs_profile_content --headed --timeout-ms 30000
curl.exe -X POST http://localhost:8001/api/import-courses
curl.exe -X POST http://localhost:8001/api/import-lectures
curl.exe -X POST "http://localhost:8001/api/import-pages?course_code=COT101&page_limit=20"
curl.exe -X POST http://localhost:8001/api/reindex-search
```

Ask test:

```powershell
$body = @{ question = "マークアップ言語って何？" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri http://localhost:8001/api/ask -Method Post -ContentType "application/json; charset=utf-8" -Body $body
```

`/api/import-pages` skips empty or login-page-looking body text, so a `/signin`
redirect will not overwrite a previously good `raw_json.extracted_text`.
`/api/import-pages` requires `course_code` for real imports. Use
`dry_run=true` to count planned pages without fetching MOOCs pages:

```powershell
curl.exe -X POST "http://localhost:8001/api/import-pages?course_code=COT101&page_limit=20&dry_run=true"
```

---

## Docker / VPS minimal startup

Before moving to a VPS, keep secrets out of Git and use `.env` locally.

1. Start Docker Desktop.
2. Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set real values. Do not commit `.env`.

Required values:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
DATABASE_URL
MEILI_URL
MEILI_MASTER_KEY
MEILI_INDEX
GEMINI_API_KEY
```

3. Build and start containers:

```powershell
docker compose up --build -d
```

4. Check Meilisearch health:

```text
http://localhost:7700/health
```

5. Initialize PostgreSQL schema:

```text
http://localhost:8000/api/init-db
```

6. Import MOOCs data in order:

```text
http://localhost:8000/api/import-courses
http://localhost:8000/api/import-lectures
http://localhost:8000/api/import-pages?course_code=COT101
http://localhost:8000/api/import-materials
http://localhost:8000/api/import-tasks
```

`/api/import-pages` requires `course_code` for real imports and waits at least
one second between page fetches. `/api/import-moocs-details` imports metadata
only and also rebuilds the Meilisearch index after importing. PostgreSQL remains
the source of truth; Meilisearch is a disposable search index.

7. Rebuild the search index from saved PostgreSQL data:

```text
http://localhost:8000/api/reindex-search
```

8. Check imported tasks:

```text
http://localhost:8000/api/tasks
```

9. Stop containers:

```powershell
docker compose down
```

Notes:

* `data/probe/moocs_course_details.json` is required by the current Docker import flow.
* Local secrets and browser login state must stay out of Git.
* PostgreSQL data is stored in the `postgres_data` Docker volume.
* Meilisearch index data is stored in the `meili_data` Docker volume and can be rebuilt from PostgreSQL.
