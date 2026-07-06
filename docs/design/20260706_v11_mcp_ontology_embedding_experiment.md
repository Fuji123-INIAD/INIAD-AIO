# INIAD-AIO v1.1 MCP / Ontology / Embedding Experiment

Date: 2026-07-06

## Purpose

v1.1 experimental evolves INIAD-AIO from a v1.0 local task/PDF demo into a local lecture context handoff base for AI agents. The branch keeps v1.0 UI and API behavior stable while adding MCP tools, lightweight ontology fields, deterministic Context Cards, and an API-key-free semantic search fallback.

## Added MCP Tools

MCP server:

```powershell
.\.venv\Scripts\python.exe -m backend.app.mcp.aio_server --base-url http://127.0.0.1:8000
```

Tools:

- `list_tasks`: returns COT101 / SEM101 / COT105 task list by default.
- `get_task_evidence`: returns evidence detail for a `task_id`.
- `list_local_resources`: returns indexed local resources.
- `search_local_resources`: searches local resources with `query`, `limit`, and `mode`.
- `get_local_resource`: returns one resource detail and text-cache summary.

The MCP layer calls the existing FastAPI API over HTTP. If the MCP server fails, the normal Web UI and REST APIs are unaffected.

## Lightweight Ontology

LocalResource now carries:

- `resource_kind`: `material | assignment | report | guide | unknown`
- `entity_type`: `resource`
- `source_kind`: `filesystem | moocs_collect | course_rule | html | slides`
- existing fields retained: `course_title`, `lecture_key`, `lecture_title`

Task list items now carry:

- `resource_kind`: assignment-like by default, report if inferred
- `entity_type`: `task`
- `source_kind`: usually `course_rule`
- `course_title`, `lecture_key`, `lecture_title`

Inference is intentionally small:

- title contains `report` / `レポート` -> `report`
- title contains `課題` / `assignment` / `homework` -> `assignment`
- title contains `講義資料` / `資料` / `Part` / `slide` -> `material`
- title contains `guide` / `利用ガイド` / `ガイド` -> `guide`
- otherwise `unknown`

Old `resource_index.json` remains readable because the API fills missing v1.1 fields from metadata at response time.

## Context Card

`card_text` is generated without an LLM from metadata templates.

Example:

```text
情報連携学概論 I 第08回 セキュリティの資料。PDFタイトルは Part1.pdf。ローカルファイルシステムからローカル保存された資料で、本文テキストは未抽出。
```

Cards are added to:

- LocalResource index output
- LocalResource API summaries and details
- Task list item API output

`/api/local/resources/search` includes `card_text` in keyword search targets.

## Embedding Fallback

Provider interface:

- `EmbeddingProvider`
- default `HashedBagOfWordsEmbeddingProvider`

Default provider:

- name: `local-hashed-bow-v1`
- dimension: 64 by default
- tokenization: ASCII words plus character n-grams
- vectorization: deterministic SHA-256 hashed bag-of-words
- normalization: L2 normalized vector
- external API keys: none
- heavy dependencies: none

Vector cache generation:

```powershell
.\.venv\Scripts\python.exe scripts\build_local_resource_vector_cache.py `
  --index data/local/resource_index.json `
  --output data/local/resource_vectors.json
```

## API Changes

Existing default remains:

```text
GET /api/local/resources/search?q=security&limit=5
```

Optional mode:

```text
GET /api/local/resources/search?q=security&limit=5&mode=keyword
GET /api/local/resources/search?q=security&limit=5&mode=semantic
GET /api/local/resources/search?q=security&limit=5&mode=hybrid
```

Response additions:

- `mode`
- per result `search_mode`
- semantic/hybrid `search_score`
- per result `resource_kind`, `entity_type`, `source_kind`, `card_text`

## What Works

- v1.0 task list and local PDF search still work.
- MCP can call the existing task/resource APIs.
- Local resources and task outputs expose lightweight ontology fields.
- Context Cards are searchable.
- Semantic and hybrid modes work offline using deterministic local vectors.
- UI can choose keyword / semantic / hybrid and displays resource kind plus card text.

## Not Yet Done

- No OCR for image-only PDFs.
- No production-grade embedding model.
- No OpenAI or sentence-transformers provider implementation yet.
- No persistent vector invalidation policy beyond the cache-generation script.
- No full ontology graph or reasoning layer.
- MCP server is intentionally minimal JSON-RPC over stdio and does not replace the Web UI.

## v1.0 Impact

v1.0 remains safe because:

- default search mode is still keyword.
- existing `/api/local/resources`, `/api/local/resources/search`, resource detail, PDF open, and task APIs keep their previous fields.
- new fields are additive.
- old `resource_index.json` files are accepted.
- `data/local/` remains runtime-only and is not committed.
