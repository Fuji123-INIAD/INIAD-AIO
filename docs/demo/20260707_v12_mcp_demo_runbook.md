# INIAD-AIO v1.2 MCP Demo Runbook

Date: 2026-07-07

This runbook is for the v1.2 presentation demo. AIO is a local MCP context
provider for task candidates and lecture-material snippets. It is not the
official source of course truth.

## Preflight

Run from the repository root:

```powershell
git status --short --branch
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Do not commit local generated data:

- `data/local/*`
- real MOOCs-Collect `db.sqlite`
- real MOOCs-Collect `search_index`
- PDFs, OCR output, cookies, `storage_state`, browser profiles
- real Claude Desktop config files, API keys, credentials
- lecture body dumps or long extracted text previews

## Build Local Material Index

This command prepares `MaterialText` and `MaterialChunk` indexes from local
MOOCs-Collect metadata and `search_index`. Outputs are ignored local files under
`data/local/`.

```powershell
.\.venv\Scripts\python.exe scripts\build_material_text_index.py `
  --resource-index data/local/resource_index.json `
  --output data/local/material_text_index.json `
  --chunk-output data/local/material_chunk_index.json `
  --moocs-collect-db "$env:APPDATA\me.yu7400ki.moocs-collect\db.sqlite" `
  --moocs-collect-root "$env:APPDATA\me.yu7400ki.moocs-collect" `
  --search-index "$env:APPDATA\me.yu7400ki.moocs-collect\search_index" `
  --include-moocs-collect `
  --include-moocs-collect-search-index
```

Optional local check:

```powershell
.\.venv\Scripts\python.exe scripts\demo_aio_mcp_chat_flow.py `
  --query "セキュリティ" `
  --course-title "情報連携学概論 I" `
  --lecture-key "08" `
  --mode keyword `
  --limit 5
```

Expected shape:

- `Text snippets / 本文あり候補` appears before `Metadata-only fallback`.
- snippet rows show `provider`, `source_type`, and `method`.
- caution says snippets may come from MOOCs-Collect `search_index` and are not guaranteed full PDF text.

## Start Backend

Terminal 1:

```powershell
$env:PYTHONPATH = "."
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## MCP Smoke Test

Terminal 2:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py `
  --base-url http://127.0.0.1:8000 `
  --query "セキュリティ" `
  --mode hybrid `
  --limit 5
```

The smoke test verifies these MCP tools are listed and callable:

- `list_pending_tasks`
- `summarize_task_backlog`
- `search_material_context`
- `get_material_context`
- `search_lecture_materials`
- `summarize_local_resource`

Expected success fields include:

- `"status": "ok"`
- `pending_task_count`
- `material_context_count`
- `material_text_snippet_count`
- `lecture_material_count`
- `material_detail_checked: true`
- `resource_summary_checked: true` when local resources exist

If the local material index is intentionally absent, rerun with
`--allow-empty-material-context` only for connectivity checks. Do not present
that as a snippet demo.

## Claude Desktop / MCP Client

Use the template in `docs/setup/claude_desktop_mcp.md`. The MCP server command is:

```powershell
.\.venv\Scripts\python.exe -m backend.app.mcp.aio_server --base-url http://127.0.0.1:8000
```

Claude Desktop should launch that command as a stdio MCP server. The server
expects FastAPI to already be available at `http://127.0.0.1:8000`.

Do not commit the real Claude Desktop config. Keep only placeholder config in
docs.

## Presentation Prompts

Task prompt:

```text
AIO MCPを使って、今確認すべき課題を教えてください。tool resultに含まれている項目だけを使い、締切や提出方法を推測で補完しないでください。
```

Material prompt:

```text
AIO MCPを使って、情報連携学概論 I のセキュリティ回の資料を探してください。本文snippetがある場合はそれに基づいて要点を整理してください。本文がない場合はmetadataのみであることを明記してください。
```

## Fallback Demo

If Claude Desktop or another MCP client is not ready, keep FastAPI running and
use the local script:

```powershell
.\.venv\Scripts\python.exe scripts\demo_aio_mcp_chat_flow.py `
  --base-url http://127.0.0.1:8000 `
  --query "セキュリティ" `
  --course-title "情報連携学概論 I" `
  --lecture-key "08" `
  --mode keyword `
  --limit 5
```

This proves the same task-backlog and material-context path through FastAPI,
but it is not an MCP client.

## Safe Claims

Say:

- AIO v1.2 can expose pending task candidates through MCP.
- AIO v1.2 can search lecture material metadata and snippets.
- AIO v1.2 can use MOOCs-Collect `search_index` as one text-like snippet provider.
- AIO v1.2 returns provider, source type, extraction method, and caution fields.
- AIO v1.2 separates text snippets from metadata-only fallback.
- AIO is a local context provider, not the official course source.

Do not say:

- AIO fully reads all lecture slides or PDFs.
- PDF text extraction is reliable for all files.
- OCR or Google Slides DOM extraction is production-ready.
- Claude or any chat AI will always answer correctly.
- AIO guarantees official deadlines, submission locations, or grading conditions.

## Failure Handling

- Backend not running: start FastAPI first, then rerun smoke.
- `material_context_count` is zero: rebuild `data/local/material_chunk_index.json`.
- `material_text_snippet_count` is zero: say metadata-only fallback is all that is available for that query, or switch to the prepared `セキュリティ` demo query.
- Claude Desktop does not show tools: verify the config uses an absolute Python path, absolute `PYTHONPATH`, and the same `--base-url`.
- Encoding looks wrong in a terminal: set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.
