# INIAD-AIO v0.3 Task List Demo Guide

Phase 3-28 時点の v0.3 を他人に見せるための起動手順と確認項目をまとめる。

## 1. v0.3 の目的

v0.3 は、INIAD-AIO をサーバー中心の検索プロトタイプから、ローカルで使える課題・資料確認ツールへ移行する途中段階である。

このデモで見せる中心機能は、Course Rule Registry から生成した課題一覧である。現時点では、MOOCs から完全な期限を自動抽出するのではなく、COT101 / SEM101 / COT105 などの既知ルールに基づいて「確認すべき課題候補」を表示する。

## 2. 起動方法

Docker Compose で起動する。

```bash
docker compose up --build
```

新しい環境で `backend/.env` がない場合は、先に作成する。

```bash
copy .env.example backend\.env
```

PowerShell 以外の環境では、同等のコピーコマンドを使う。

起動後、FastAPI backend は `http://localhost:8000` で待ち受ける。PostgreSQL と Meilisearch も同時に起動するが、今回の課題一覧デモは主に rule-based task list と local JSON status 保存を見る。

## 3. 確認 URL

Frontend:

```text
http://localhost:8000/
```

Task list API:

```text
http://localhost:8000/api/tasks?course_code=COT101&course_code=SEM101&course_code=COT105
```

Evidence detail API example:

```text
http://localhost:8000/api/tasks/course-rule:COT101/evidence
```

## 4. できること

### 課題一覧表示

トップページを開くと、COT101 / SEM101 / COT105 の rule-based task list が表示される。

API では次のような情報を確認できる。

- `task_count`
- `active_count`
- `items[].task_id`
- `items[].course_code`
- `items[].status`
- `items[].evidence`
- `items[].evidence_detail_url`

Phase 3-27 smoke test では、COT101 / SEM101 / COT105 の `task_count` は `3` として確認している。

### status 変更

Frontend の status select から、各 task を次の状態に変更できる。

- `todo`
- `done`
- `ignored`

変更すると `PATCH /api/tasks/{task_id}/status` が呼ばれ、次回の `/api/tasks` 取得結果に反映される。

### local JSON 永続化

status は local JSON に保存される。

既定の保存先:

```text
data/local/user_task_status.json
```

Docker 起動時は `./data:/app/data` が volume mount されるため、コンテナを作り直しても host 側の `data/local/user_task_status.json` に残る。

### evidence summary / detail

一覧 API の `items[].evidence` は軽量 summary である。表示用に次の最小情報だけを返す。

- `type`
- `label`
- `confidence`

詳細な `source` は一覧 API には含めない。必要な場合は `items[].evidence_detail_url` を開く。

Detail API:

```text
GET /api/tasks/{task_id}/evidence
```

Detail API では `source` を含む full evidence を返す。Phase 3-25 時点では、HTML evidence と Slides evidence を扱う。Slides evidence は既存の MOOCs probe JSON と、任意の MOOCs-Collect `db.sqlite` page_key listing 成果を利用する。

## 5. できないこと

### 自動 deadline 抽出

現時点の task list は、実 MOOCs の提出期限を自動抽出して確定 deadline として扱うものではない。

deadline は今後の実装対象であり、このデモでは rule-based な課題候補表示を確認する。

### ユーザー別認証

このデモにはユーザー認証・ユーザー別権限管理はない。

status はローカル JSON に保存されるだけであり、複数ユーザーを分けて扱わない。

### 本格 DB 永続化

v0.3 の設計上は SQLite local DB への移行を進めているが、この task list demo の status 保存は JSON ベースである。

PostgreSQL は既存 API や compose 構成のために起動するが、今回の task list status の主保存先ではない。

### Playwright リアルタイム解析

通常の `/api/tasks` path では Playwright を実行しない。

MOOCs へのログイン、ブラウザ操作、リアルタイム page 解析はこのデモの範囲外である。Slides evidence も、既存 probe JSON または read-only の MOOCs-Collect DB metadata を使う。

## 6. smoke test 実行方法

v0.3 smoke test だけを実行する。

```bash
.\.venv\Scripts\python.exe -m unittest tests.test_v03_smoke
```

全テストを実行する。

```bash
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Phase 3-27 smoke test の確認対象:

- `/api/tasks` が `200` を返す
- COT101 / SEM101 / COT105 の `task_count` が期待通り
- status PATCH 後に `/api/tasks` に反映される
- `user_task_status.json` に保存される
- `/api/tasks/{task_id}/evidence` が `200` を返す
- `frontend/index.html` が必要な API を参照している
- `MOOCS_COLLECT_DB_PATH` 未設定でも落ちない

## 7. 注意事項

- `MOOCS_COLLECT_DB_PATH` は任意設定である。未設定でも task list は動く。
- `MOOCS_COLLECT_DB_PATH` を設定する場合も、通常 API path では read-only metadata 参照に留める。
- evidence detail の `source` には MOOCs URL、Slides URL、または page_key が入る場合がある。
- `data/local/user_task_status.json` はデモ中に書き換わる。初期状態に戻したい場合は、このファイルを退避または削除してから起動する。
- このデモは Phase 3-28 時点の途中成果であり、deadline 自動抽出、ユーザー別認証、本格的な local DB 永続化、Playwright によるリアルタイム MOOCs 解析は含まない。
