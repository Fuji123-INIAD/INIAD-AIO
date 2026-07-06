# INIAD-AIO

INIAD-AIO は、INIAD（東洋大学情報連携学部）向けの AI 情報アクセス基盤です。

MOOCs を中心とした講義・課題・資料情報を収集・整理し、自然言語で検索・参照できる環境の構築を目的としています。

現在は **v1.0 発表版** の準備中です。

---

## はじめに

このリポジトリは現在も大きく構造変更中です。

初見の場合、ソースコードを直接読む前に、まず Overview 系ドキュメントを参照してください。

---

## AI に読ませる場合

このリポジトリを AI アシスタントに説明・編集・解析させる場合は、GeeKEN Discord で共有されている Overview / Context documents を読ませてください。

これらには以下が定義されています。

- INIAD-AIO の目的
- 現在の実装状況
- 未実装範囲
- プロジェクト固有語彙
- 初心者向け説明方針

特定機能について扱う場合は、対応する Node Overview / Node Vocabulary も追加で参照してください。

ファイル名やディレクトリ構造のみから推測せず、Overview を優先的なコンテキストとして扱ってください。

---

## 現在の状態（v1.0 発表版）

現在実装・検証中の主な要素:

- FastAPI backend
- COT101 / COT105 / SEM101 の課題候補一覧
- 課題 status のローカルJSON永続化
- MOOCs-Collect が保存したPDFのローカル discovery
- PDFテキストレイヤー抽出と `data/local/text_cache/` 保存
- ローカルPDF検索API
- 課題一覧とPDF検索の最小UI

発表版では、ローカルで確実に動く課題確認とPDF資料検索を優先しています。

---

## 未完成・未安定な要素

以下は未完成、または実験段階です。

- Embedding 検索
- OCR
- MCP 連携
- 本格 Ontology
- 本格 RAG
- 本番認証基盤
- 大規模 multi-source ingestion
- 安定 UI
- 権限管理

---

## 開発

```bash
docker compose up --build
```

API:

```txt
http://localhost:8000
```

---

## ドキュメント方針

README は入口のみを担当します。

詳細説明・意味構造・開発意図・変更履歴は以下に分離されています。

- Overview
- ACV (Atlas Compressed Vocabulary)
- CEL（Concrete Edit Log）

大規模変更時は README を肥大化させるのではなく、対応する Overview または CEL を更新してください。

## v1.1 experimental

`feature/v1.1-adventure-mcp-ontology` adds an experimental AI handoff layer without changing the v1.0 stable demo path:

- Minimal MCP server: `python -m backend.app.mcp.aio_server --base-url http://127.0.0.1:8000`
- MCP tools for tasks and local resources.
- Lightweight ontology fields on tasks/resources.
- Template-generated `card_text` Context Cards.
- Offline semantic/hybrid search fallback using `local-hashed-bow-v1`.
- Optional vector cache script: `python scripts/build_local_resource_vector_cache.py`

Design note: `docs/design/20260706_v11_mcp_ontology_embedding_experiment.md`

## v1.2 experimental

`feature/v1.2-mcp-chat-materials-experiment` extends the MCP path so chat AI clients can retrieve safer task backlog summaries and bounded lecture-material snippets.

- New MCP task tools: `list_pending_tasks`, `summarize_task_backlog`
- New material model: `MaterialText` / `MaterialChunk`
- New material search APIs: `/api/materials`, `/api/materials/search`, `/api/context/search`
- New MCP material tools: `search_material_context`, `get_material_context`, `search_lecture_materials`, `summarize_local_resource`
- Index build script: `python scripts/build_material_text_index.py`
- MOOCs-Collect probe: `python scripts/probe_moocs_collect_text_quality.py`
- OCR availability probe: `python scripts/probe_pdf_text_extractors.py`
- Demo fallback: `python scripts/demo_aio_mcp_chat_flow.py`

`data/local/`, MOOCs-Collect `db.sqlite`, PDFs, OCR outputs, storage state, cookies, browser profiles, Claude Desktop config, and credentials must not be committed.

Design notes:

- `docs/design/20260706_v12_chat_ai_mcp_materials_experiment.md`
- `docs/design/material_text_pipeline.md`
- `docs/setup/claude_desktop_mcp.md`
