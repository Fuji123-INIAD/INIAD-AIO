# 2026-07-08 v1.4 AI-Ready MCP Context Handoff

- Current branch: `feature/v1.4-ai-ready-mcp-context`
- Latest implementation commit before this handoff: `c1d1b33 Add AI-ready MCP context pack`
- Presentation branch: `demo/v1.2-presentation-20260708` remains at `939544d77c1e5d08470f0f7fd6b76e34ae6707f0`; origin matches.
- Pushed: not yet at the time this handoff was written.
- Git status before this handoff file: clean except this new handoff file.
- Changed files in implementation: `README.md`, `backend/app/core/ai_context_pack.py`, `backend/app/mcp/aio_server.py`, `backend/main.py`, `scripts/smoke_aio_mcp.py`, `tests/test_ai_context_pack.py`, `tests/test_aio_mcp_server.py`, `docs/design/20260708_v14_ai_ready_mcp_context.md`
- Tests run: `.\.venv\Scripts\python.exe -m unittest discover -s tests` -> 171 tests OK
- MCP smoke run: required command against `127.0.0.1:8000` initially hit an older existing backend and returned 404 for `/api/context/ai-pack`; current-code backend was then run on a temporary port and `scripts\smoke_aio_mcp.py --base-url http://127.0.0.1:8014 --query "セキュリティ" --mode hybrid --limit 5` -> OK. Later 8000 was found occupied by another process, so it was not stopped.
- Completed: added API `GET /api/context/ai-pack` and MCP tool `prepare_course_context`; smoke now verifies the new tool. The pack separates `tasks.rule_based`, `tasks.moocs_derived`, `materials.text_snippets`, and `materials.metadata_only`, preserving source/provenance/confidence/caution/open URL fields.
- What works: Claude/MCP clients can request task candidates plus bounded lecture-material snippets in one AI-ready context pack. Existing task/material MCP tools remain compatible.
- What does not work / not guaranteed: no OCR rollout, no default Google Slides DOM crawling, no full-course MOOCs sync, no official deadline/submission/grading guarantees, and no full lecture-text guarantee.
- Next recommended task: restart the user-facing FastAPI backend from this branch on port 8000, then run the required smoke command against 8000 and test from Claude Desktop.
- Do not commit: `data/local/*`, AppData contents, real `db.sqlite`, real `search_index`, PDFs, OCR output, cookies, `storage_state`, browser profiles, real Claude Desktop config, API keys, credentials, lecture body dumps, long raw previews, private caches, or private indexes.
