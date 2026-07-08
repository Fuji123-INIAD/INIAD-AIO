# 2026-07-08 v1.4 Claude MCP Stabilization Handoff

- Current branch: `feature/v1.4-ai-ready-mcp-context`
- Latest implementation commit before this handoff: `4c09023 Stabilize Claude MCP context output`
- Pushed: not yet
- Git status before writing this handoff: clean, branch ahead of origin by 1 commit
- Changed implementation files: `README.md`, `backend/app/core/ai_context_pack.py`, `backend/app/mcp/aio_server.py`, `docs/design/20260708_v14_ai_ready_mcp_context.md`, `docs/setup/claude_desktop_mcp.md`, `scripts/smoke_aio_mcp.py`, `tests/test_ai_context_pack.py`, `tests/test_aio_mcp_server.py`
- Completed: `prepare_course_context` still fetches the full `/api/context/ai-pack` JSON internally, but MCP `tools/call` now returns short sanitized Markdown in `content[0].text` and only compact counts in `structuredContent`.
- Completed: MCP formatter includes query, task count, text snippet count, metadata-only count, task candidates, up to 5 snippets, up to 3 metadata-only fallbacks, provider/source/extraction fields, and caution lines.
- Completed: MCP stdio setup now reconfigures stdin/stdout/stderr for UTF-8 without emitting non-protocol output. Search for stdout/debug output found only the JSON-RPC response print in `aio_server.py`.
- API compatibility: `GET /api/context/ai-pack?q=セキュリティ` on `127.0.0.1:8000` still returned full JSON with `status=ok`, `pack_type=ai_ready_task_material_context`, 1 task candidate, 7 text snippets, and 1 metadata-only fallback in the local dataset.
- Tests run: `.\.venv\Scripts\python.exe -m unittest discover -s tests` -> 173 tests OK.
- Targeted tests run: `.\.venv\Scripts\python.exe -m unittest tests.test_ai_context_pack tests.test_aio_mcp_server` -> 13 tests OK.
- Smoke run: `.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py --base-url http://127.0.0.1:8000 --query "セキュリティ" --mode hybrid --limit 5` -> OK, compact text length 2734.
- Smoke run: same command with `--limit 8` -> OK, compact text length 2942, 7 text snippets and 1 metadata-only fallback in the AI context summary.
- Remaining issues: real Claude Desktop UI call still needs a manual retry after reloading Claude Desktop config. The backend on port 8000 was already running and was not restarted by this task.
- Next step: restart Claude Desktop, use the documented `cmd.exe` UTF-8 wrapper config in `docs/setup/claude_desktop_mcp.md`, then call `prepare_course_context` with query `セキュリティ`.
- Do not commit: `data/local/*`, AppData contents, real `db.sqlite`, real `search_index`, PDFs, OCR output, cookies, `storage_state`, browser profiles, real Claude Desktop config, API keys, credentials, lecture body dumps, long raw previews, private caches, or private indexes.
