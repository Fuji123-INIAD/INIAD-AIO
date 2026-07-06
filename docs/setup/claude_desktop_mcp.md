# Claude Desktop MCP Setup

Use the MCP server only after the FastAPI backend is running.

## Backend

```powershell
cd C:\path\to\INIAD-AIO
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

`PYTHONPATH` should resolve to the repository root. If your client launches from another directory, set it explicitly to the absolute repo path.

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

```powershell
.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py `
  --base-url http://127.0.0.1:8000 `
  --query "セキュリティ" `
  --mode hybrid `
  --limit 5
```

## Presentation Prompts

```text
AIO MCPを使って、今確認すべき課題を教えてください。tool resultに含まれている項目だけを使い、締切や提出方法を推測で補完しないでください。
```

```text
AIO MCPを使って、情報連携学概論 I のセキュリティ回の資料を探してください。本文snippetがある場合はそれに基づいて要点を整理してください。本文がない場合はmetadataのみであることを明記してください。
```
