# v1.2 Material Search Quality Handoff

Date: 2026-07-06
Branch: feature/v1.2-mcp-chat-materials-experiment
Latest base commit before this task: a552129 Tighten v1.2 demo snippet display

## Scope

- Improved material search ranking with synthetic fixtures only.
- Did not enable OCR or Playwright DOM extraction by default.
- Did not change MaterialText/MaterialChunk provider design or API response compatibility.
- Did not read or commit real `data/local`, AppData, DB, search index, PDF, OCR output, credentials, or lecture body dumps.

## Changed Files

- `backend/app/core/material_search.py`
- `scripts/evaluate_material_search.py`
- `tests/test_material_search_quality.py`
- `docs/context/20260706_v12_search_quality_handoff.md`

## Completed

- Added `scripts/evaluate_material_search.py` with synthetic chunks for repeatable ranking evaluation.
- Reproduced a partial-filter ranking issue where a partial `course_title` / `lecture_key` match could outrank an exact COT105/08 match.
- Added a small filter match boost so exact course/lecture/source filters rank above partial matches.
- Added result diversification so the same `material_id` does not occupy the top slots when alternatives exist.
- Kept text-bearing chunks ahead of metadata-only fallback chunks.
- Added tests for text-vs-metadata ranking, exact filter boost, duplicate material suppression, and provider/source_type/method preservation.

## Verification So Far

- `.\.venv\Scripts\python.exe -m unittest tests.test_material_search_quality`
- `.\.venv\Scripts\python.exe scripts\evaluate_material_search.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_material_pipeline tests.test_local_resource_api tests.test_moocs_collect_v12_providers`

All passed before this handoff file was written.

## Next Required Checks

- Run `.\.venv\Scripts\python.exe scripts\evaluate_material_search.py --help`
- Run `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Check `git status --short --untracked-files=all`
- Check `git diff --stat`
- Confirm no generated local data or sensitive files are staged.
- Commit the synthetic evaluation and ranking improvements.

## Remaining Issues

- `search_index` text can still contain extraction noise.
- This does not prove complete lecture full-text extraction.
- The evaluation fixture is synthetic and should be complemented by non-committed local checks before demos.
