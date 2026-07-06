# INIAD-AIO v1.2 Chat AI MCP Materials Experiment

Date: 2026-07-06

## Goal

v1.2 moves AIO closer to a local context substrate for chat AI clients such as Claude Desktop. The important path is not a browser-first PDF search UI, but MCP tools that safely expose:

- pending task candidates
- local lecture material metadata
- PDF text cache when available
- MOOCs-Collect slide text when available
- MOOCs HTML cache text when available
- bounded MaterialChunk snippets with source labels and caution text

## Safety Rules

- Do not commit `data/local/`, real PDFs, OCR outputs, cookies, storage state, browser profiles, Claude Desktop config, API keys, or MOOCs-Collect `db.sqlite`.
- MOOCs-Collect DB access must be read-only.
- MCP stdout must contain JSON-RPC only. Tool text is serialized with ASCII-safe JSON.
- Task tools must not infer deadlines, submission methods, submission destinations, or grading conditions.
- Material tools must say that snippets can come from MOOCs-Collect, MOOCs HTML, or metadata, not necessarily a normal PDF text layer.

## MCP Tools Added

- `list_pending_tasks`
- `summarize_task_backlog`
- `search_material_context`
- `get_material_context`
- `search_lecture_materials`
- `summarize_local_resource`

Existing v1.1 tools remain:

- `list_tasks`
- `get_task_evidence`
- `list_local_resources`
- `search_local_resources`
- `get_local_resource`

## API Added

- `GET /api/tasks/pending`
- `GET /api/tasks/backlog/summary`
- `GET /api/materials`
- `GET /api/materials/search?q=&mode=&limit=`
- `GET /api/materials/{material_id}`
- `GET /api/materials/{material_id}/chunks`
- `GET /api/context/search?q=&mode=&limit=`

If `data/local/material_text_index.json` or `data/local/material_chunk_index.json` is missing, the API falls back to `resource_index.json` and in-memory chunks.

## Scripts Added

```powershell
.\.venv\Scripts\python.exe scripts\build_material_text_index.py --help
.\.venv\Scripts\python.exe scripts\probe_moocs_collect_text_quality.py --help
.\.venv\Scripts\python.exe scripts\probe_pdf_text_extractors.py --help
.\.venv\Scripts\python.exe scripts\demo_aio_mcp_chat_flow.py --help
```

The main build command writes ignored outputs under `data/local/`:

```powershell
.\.venv\Scripts\python.exe scripts\build_material_text_index.py `
  --resource-index data/local/resource_index.json `
  --output data/local/material_text_index.json `
  --chunk-output data/local/material_chunk_index.json `
  --include-pdf-cache `
  --include-moocs-collect `
  --moocs-collect-db "C:\path\to\MOOCs-Collect\db.sqlite"
```

## Current Limitation

The MOOCs-Collect provider can read text columns found in the `slides` table, including SVG/HTML-like aria-label text. If the real app stores searchable text in another table or index directory, run `probe_moocs_collect_text_quality.py` and extend the provider mapping.

OCR is only an optional probe. Heavy OCR dependencies are not required for normal tests or demos.
