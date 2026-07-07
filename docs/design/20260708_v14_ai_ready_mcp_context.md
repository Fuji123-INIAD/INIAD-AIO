# INIAD-AIO v1.4 AI-Ready MCP Context

Date: 2026-07-08

## Goal

v1.4 adds one MCP path that returns task candidates and lecture-material snippets
together as a compact context pack for chat AI use.

The new MCP tool is:

- `prepare_course_context`

The backing API is:

- `GET /api/context/ai-pack`

Existing tools remain compatible:

- `list_tasks`
- `list_pending_tasks`
- `summarize_task_backlog`
- `search_material_context`
- `get_material_context`

## Example MCP Arguments

```json
{
  "query": "セキュリティ",
  "course_title": "情報連携学概論 I",
  "lecture_key": "08",
  "mode": "hybrid",
  "material_limit": 5,
  "task_limit": 8,
  "snippet_chars": 360
}
```

## Example API Check

With FastAPI running:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/context/ai-pack?q=セキュリティ&course_title=情報連携学概論%20I&lecture_key=08&mode=hybrid&material_limit=5"
```

The required MCP smoke also calls `prepare_course_context`:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_aio_mcp.py `
  --base-url http://127.0.0.1:8000 `
  --query "セキュリティ" `
  --mode hybrid `
  --limit 5
```

## Pack Shape

Top-level fields:

- `pack_type`: `ai_ready_task_material_context`
- `instructions`: short instruction telling the AI not to infer missing official facts
- `tasks.rule_based`: rule-based task candidates
- `tasks.moocs_derived`: MOOCs-derived task candidates, when `data/local/moocs_task_candidates.json` is available
- `materials.text_snippets`: text-bearing snippets
- `materials.metadata_only`: metadata-only fallback entries
- `cautions`: task, material, and overall caution strings
- `warnings`: loader/index warnings

Task entries preserve:

- `source`
- `source_kind`
- `kind`
- `confidence`
- `deadline_text`
- `deadline_confidence`
- `submission_text`
- `submission_confidence`
- `submission_format_text`
- `submission_format_confidence`
- `open_url`
- `evidence_summary`
- `evidence_url`

Material entries preserve:

- `provider`
- `source_type`
- `extraction_method`
- `source_kind`
- `confidence`
- `open_url`
- `metadata_only`
- bounded `snippet`

## Safety Notes

- AIO is a local context provider, not the official course source.
- Official deadlines, submission destinations, formats, and grading conditions must not be inferred.
- Missing task fields stay `unknown` or low confidence.
- Material snippets may come from MOOCs-Collect `search_index`, MOOCs HTML, PDF text cache, or metadata fallback.
- Metadata-only fallback is intentionally separated from text snippets.
- Do not commit `data/local/*`, AppData, real `db.sqlite`, real `search_index`, PDFs, credentials, storage state, cookies, browser profiles, or lecture body dumps.
