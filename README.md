# INIAD-AIO

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

Use persistent profile login for the most stable MOOCs session:

```powershell
python backend\moocs_probe.py --details --details-limit 1 --lesson-limit 2 --page-limit 2 --profile-dir data/probe/moocs_profile --headed --verbose
```

Limits:

* `--details-limit N`: max courses to visit.
* `--lesson-limit N`: max lesson groups per course.
* `--page-limit N`: max lesson pages per lesson group.

The details output is metadata-only. It does not store raw body text or `text_preview`.
