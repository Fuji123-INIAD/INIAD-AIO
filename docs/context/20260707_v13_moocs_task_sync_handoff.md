# 2026-07-07 v1.3 MOOCs Task Sync Handoff

- Current branch: `feature/v1.3-moocs-real-task-sync`
- Presentation branch: `demo/v1.2-presentation-20260708` remains at `939544d77c1e5d08470f0f7fd6b76e34ae6707f0`; origin matches.
- Latest implementation commit before this handoff: `f2543bc Add COT105 MOOCs-derived task MVP`
- Pushed: not yet after `f2543bc` at the time this handoff was written
- Git status before this handoff file: clean except this new handoff file; feature branch ahead of origin by 1
- Changed files in MVP: `backend/app/core/moocs_task_candidates.py`, `backend/app/core/task_generator.py`, `backend/app/core/task_list_composer.py`, `backend/app/core/task_backlog.py`, `backend/app/core/ontology.py`, `backend/app/core/context_cards.py`, `backend/main.py`, `tests/fixtures/moocs_cot105_task_candidates_sanitized.json`, `tests/test_moocs_task_candidates.py`, `tests/test_task_list_api.py`, `tests/test_list_rule_tasks.py`
- Tests run: `.\.venv\Scripts\python.exe -m unittest discover -s tests` -> 168 tests OK
- MCP smoke run: `.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py --base-url http://127.0.0.1:8000 --query "セキュリティ" --mode hybrid --limit 5` -> OK
- Completed: added optional `data/local/moocs_task_candidates.json` path for runtime MOOCs-derived task candidates; missing file is skipped. Added COT105 sanitized fixture tests. Rule-based and MOOCs-derived tasks are separated by `source`, `source_kind`, `kind`, `confidence`, and `evidence`.
- What works: `/api/tasks`, `/api/tasks/pending`, `/api/tasks/backlog/summary`, and evidence detail can include COT105 MOOCs-derived tasks without removing rule-based candidates. Unknown deadline/submission fields stay `unknown` or low confidence unless explicit data exists.
- What does not work / not guaranteed: no live MOOCs login/sync, no full-course rollout, no official deadline/submission/grading guarantee, and no real AppData/DB/search_index/PDF ingestion for tasks yet.
- Next recommended task: build a local non-committed script/import path that writes sanitized MOOCs task candidate JSON under `data/local/moocs_task_candidates.json` from authenticated user-controlled probing.
- Do not commit: `data/local/*`, AppData contents, real `db.sqlite`, real `search_index`, PDFs, OCR output, cookies, `storage_state`, browser profiles, real Claude Desktop config, API keys, credentials, lecture body dumps, long raw previews, private caches, or private indexes.
