# Claude Desktop MCP Setup

Use the MCP server only after the FastAPI backend is running. Keep real Claude
Desktop config files local; commit only placeholder examples like this document.

## Backend

```powershell
cd C:\path\to\INIAD-AIO
$env:PYTHONPATH = "."
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

`PYTHONPATH` should resolve to the repository root. If your client launches from another directory, set it explicitly to the absolute repo path.

## Material Index For Snippets

For the v1.2 material-snippet demo, build the ignored local indexes before
starting Claude Desktop. The command reads local MOOCs-Collect data but writes
only under `data/local/`, which must not be committed.

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

Do not commit `data/local/*`, the real `db.sqlite`, the real `search_index`, or
raw lecture text dumps.

## MCP Server Command

Use the absolute repo path in Claude Desktop config. Do not commit your real config file.

```json
{
  "mcpServers": {
    "iniad-aio": {
      "command": "C:\\path\\to\\INIAD-AIO\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "backend.app.mcp.aio_server",
        "--base-url",
        "http://127.0.0.1:8000"
      ],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\INIAD-AIO",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

## Smoke

Run this from a second terminal while FastAPI is running. The smoke script uses
the in-process JSON-RPC MCP handler and verifies these v1.2 tools are callable:
`list_pending_tasks`, `summarize_task_backlog`, `search_material_context`,
`get_material_context`, `search_lecture_materials`, and
`summarize_local_resource`.

```powershell
.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py `
  --base-url http://127.0.0.1:8000 `
  --query "セキュリティ" `
  --mode hybrid `
  --limit 5
```

Expected result: JSON with `"status": "ok"`, nonzero material context counts for
the prepared demo data, and `material_text_snippet_count` above zero. If the
local material index is intentionally unavailable, use the fallback demo script
from `docs/demo/20260707_v12_mcp_demo_runbook.md` and say that only metadata
fallback was available.

## Presentation Prompts

```text
AIO MCPを使って、今確認すべき課題を教えてください。tool resultに含まれている項目だけを使い、締切や提出方法を推測で補完しないでください。
```

```text
AIO MCPを使って、情報連携学概論 I のセキュリティ回の資料を探してください。本文snippetがある場合はそれに基づいて要点を整理してください。本文がない場合はmetadataのみであることを明記してください。
```
