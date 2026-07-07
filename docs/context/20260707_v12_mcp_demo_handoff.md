# 2026-07-07 v1.2 MCP Demo Handoff

- Current branch: `feature/v1.2-mcp-chat-materials-experiment`
- Latest implementation commit before this handoff: `f294e02 Prepare v1.2 MCP demo workflow`
- Pushed: not yet after local Codex commits
- Git status before this handoff file: clean, branch ahead of origin by 3
- Changed files in demo workflow commit: `README.md`, `backend/app/mcp/aio_server.py`, `scripts/smoke_aio_mcp.py`, `tests/test_aio_mcp_server.py`, `docs/setup/claude_desktop_mcp.md`, `docs/demo/20260707_v12_mcp_demo_runbook.md`, `docs/demo/20260708_v10_demo_guide.md`
- Tests run: `.\.venv\Scripts\python.exe -m unittest discover -s tests` -> 162 tests OK
- Extra checks run: `scripts\smoke_aio_mcp.py --help`, `scripts\evaluate_material_search.py --help`, targeted unittest for MCP/material/demo display -> OK
- Live MCP smoke run: `.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py --base-url http://127.0.0.1:8000 --query "セキュリティ" --mode hybrid --limit 5` -> OK; 11 tools listed, 1 pending task, 5 material context items, 3 text snippets, 2 metadata-only fallback rows
- Fallback demo run: `.\.venv\Scripts\python.exe scripts\demo_aio_mcp_chat_flow.py --base-url http://127.0.0.1:8000 --query "セキュリティ" --course-title "情報連携学概論 I" --lecture-key "08" --mode keyword --limit 5` -> OK
- What works: MCP smoke now actually calls v1.2 task/material tools, checks caution fields, checks provider/source_type/extraction_method, checks metadata/text indicators, and verifies material/resource detail calls.
- What does not work / not guaranteed: AIO still does not guarantee complete lecture full-text extraction, perfect PDF extraction, OCR readiness, Google Slides DOM production readiness, official deadlines, submission rules, or chat AI answer correctness.
- Demo docs: use `docs/demo/20260707_v12_mcp_demo_runbook.md`; Claude Desktop template is in `docs/setup/claude_desktop_mcp.md`.
- Next recommended task: do a final presentation dry run in Claude Desktop, then push the local commits if the run is acceptable.
- Do not commit: `data/local/*`, AppData contents, real `db.sqlite`, real `search_index`, PDFs, OCR output, cookies, `storage_state`, browser profiles, real Claude Desktop config, API keys, credentials, lecture body dumps, long raw previews, private caches, or private indexes.
