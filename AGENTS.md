# AGENTS.md

## Project

This repository is INIAD-AIO.

The current goal is to make AIO useful as a local MCP-based context provider for INIAD tasks and lecture materials.

The priority is not a polished browser UI. The priority is a reliable local workflow where a chat AI can call MCP tools to retrieve:

- task candidates
- lecture material metadata
- relevant material snippets
- context packs for downstream chat AI use

AIO should mainly provide grounded context. It should not pretend to be the final source of truth.

## Current branch focus

The current active work is around:

- `feature/v1.2-mcp-chat-materials-experiment`

The current v1.2 focus is:

- MCP tools for task backlog and lecture materials
- MOOCs-Collect integration
- MaterialText / MaterialChunk / Context Pack pipeline
- `search_index` provider support
- demo-ready MCP workflow for presentation

## Current demo target

Prepare a v1.2 demo-ready implementation for the upcoming presentation.

The demo-ready target is:

- MCP tools can return pending task candidates.
- MCP tools can summarize task backlog.
- MCP tools can return lecture material search results.
- Material search can return text snippets when available.
- Metadata-only fallback is clearly separated from text snippets.
- Provider, source_type, extraction method, and caution fields are preserved.
- A local smoke test or demo script can prove the workflow.
- Documentation explains how to run the demo.
- Documentation explains what is not guaranteed.
- All tests pass.
- No private local data or lecture-body dumps are committed.

## Current known findings

MOOCs-Collect findings:

- `db.sqlite` is a metadata ledger, not the primary lecture-body text store.
- `db.sqlite` contains structures such as courses, lectures, pages, and slides.
- The text-like searchable content appears to be in MOOCs-Collect `search_index`.
- The `search_index` is a Tantivy index.
- AIO should treat `search_index` as a provider for text-like snippets.
- `slides.url` may point to Google Slides embed/pubembed URLs.
- PDF native text extraction may be sparse or noisy.
- OCR and Playwright DOM extraction should remain optional and default-off unless explicitly requested.

AIO should continue to support fallback behavior:

- search_index text snippets
- MOOCs / HTML text if available
- local PDF metadata
- local resource metadata
- metadata-only fallback

## Do not overclaim

Do not describe the current system as if it can fully read all lecture materials.

Safe wording:

- AIO can retrieve task candidates and lecture-material-related snippets.
- AIO can use MOOCs-Collect `search_index` as one provider for text-like snippets.
- AIO can return context packs for use by a chat AI.
- AIO can separate text snippets from metadata-only fallback results.
- AIO can expose provider and source information so downstream AI can be cautious.

Unsafe wording:

- AIO can fully read all lecture slides.
- AIO can fully read all PDFs.
- PDF text extraction is reliable for all files.
- OCR is production-ready.
- Google Slides DOM extraction is production-ready.
- Claude or any chat AI will always answer correctly from the materials.
- The system guarantees official deadlines, submission locations, or grading conditions.

For tasks and deadlines, always preserve the caution that MOOCs or other official course pages are authoritative.

## Strict commit restrictions

Never commit:

- `data/local/*`
- AppData contents
- `db.sqlite`
- MOOCs-Collect `search_index` files
- PDFs
- OCR output files
- cookies
- `storage_state` files
- browser profiles
- real Claude Desktop config files
- API keys
- credentials
- lecture body dumps
- long raw extracted text previews
- private local cache files
- private generated indexes
- private user data

If documentation needs a path, use placeholders or clearly marked examples.

Acceptable example path style:

- `%APPDATA%\me.yu7400ki.moocs-collect\db.sqlite`
- `%APPDATA%\me.yu7400ki.moocs-collect\search_index`
- `C:\path\to\INIAD-AIO`

Avoid committing the user's exact private local configuration unless it is already generic and necessary.

## Long-running Codex rules

Use small task units.

Preferred loop:

1. Inspect current branch and status.
2. Read relevant handoff docs.
3. Make a small plan.
4. Implement one coherent improvement.
5. Run tests.
6. Check `git status`.
7. Check `git diff --stat`.
8. Confirm no forbidden files or data are included.
9. Commit.
10. Write or update a handoff Markdown file.
11. Continue only after the checkpoint is clean.

When context usage reaches about 80%:

- Stop expanding scope.
- Write a handoff Markdown file under `docs/context/`.
- Include branch, latest commit, changed files, test results, completed work, remaining issues, next steps, and forbidden commit reminders.
- Compact if needed.
- After compaction, reread the handoff file before continuing.

When context usage reaches about 90%:

- Stop new implementation.
- Run tests.
- Check `git status`.
- Check `git diff --stat`.
- Prepare commit or handoff.

When context usage reaches about 95%:

- Do not continue implementation.
- Write a final handoff Markdown file.
- Stop.

Do not paste huge logs into chat. Summarize failures and inspect files locally.

## Required checks before every commit

Before every commit, run or explain why you cannot run:

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- `git status`
- `git diff --stat`

Also inspect staged files before committing.

Do not commit generated local indexes, real databases, PDFs, credentials, or extracted lecture text dumps.

## Demo priority

For the v1.2 presentation, prioritize:

1. MCP smoke test.
2. Claude Desktop or MCP client connection instructions.
3. Demo documentation.
4. Fallback script demo if MCP client setup fails.
5. Clear caution text.
6. Tests.
7. Handoff docs.
8. Clean git history with small commits.

Do not prioritize:

- Large OCR implementation.
- Google Slides DOM crawling by default.
- Large embedding implementation.
- Major UI redesign.
- Major refactor unrelated to the demo.
- Full browser app polish.
- Full production deployment.

## MCP tools of interest

Important MCP tools include:

- `list_pending_tasks`
- `summarize_task_backlog`
- `search_material_context`
- `get_material_context`
- `search_lecture_materials`
- `summarize_local_resource`

Existing tools should not be broken.

When changing MCP outputs, preserve caution fields and source/provenance information.

## API and pipeline areas

Important API / pipeline areas include:

- task backlog APIs
- material APIs
- context search APIs
- `MaterialText`
- `MaterialChunk`
- `Context Pack`
- material search ranking
- provider/source metadata
- metadata-only fallback behavior

Avoid unnecessary incompatible API changes.

## Material search quality goals

Material search should prefer:

- text snippets over metadata-only fallback when both are relevant
- exact `course_title` matches over partial matches
- exact `lecture_key` matches over partial matches
- relevant lecture/material title matches
- fewer duplicate top results from the same material
- clear provider/source metadata

Material search should preserve:

- `provider`
- `source_type`
- `extraction_method`
- `metadata-only` indication
- caution text
- open availability when appropriate

Do not hide uncertainty.

## Documentation expectations

When adding or changing demo behavior, update or create docs under:

- `docs/demo/`
- `docs/context/`
- `docs/design/`
- `docs/research/`

For handoff docs, include:

- current branch
- latest commit
- pushed or not
- git status
- changed files
- tests run
- demo commands
- what works
- what does not work
- remaining issues
- next recommended task
- commit restrictions reminder

Keep handoff docs concise. Do not paste long extracted lecture text.

## Presentation-safe claims

The presentation may say:

- AIO v1.2 can expose pending task candidates through MCP.
- AIO v1.2 can search lecture material metadata and snippets.
- AIO v1.2 can use MOOCs-Collect `search_index` as a text-like snippet provider.
- AIO v1.2 can return context with source/provenance metadata.
- AIO v1.2 separates text snippets from metadata-only fallback.
- AIO v1.2 is a local context provider, not the official source of course truth.

The presentation should not say:

- AIO fully understands all lecture materials.
- AIO guarantees all deadlines or submission rules.
- AIO has perfect PDF extraction.
- AIO has production-ready OCR.
- AIO has production-ready Google Slides DOM extraction.
- AIO guarantees correct answers from Claude or any other AI.

## Windows / PowerShell preference

The main development environment is Windows PowerShell.

Prefer commands that work in PowerShell.

Use the local virtual environment:

- `.\.venv\Scripts\python.exe`

Typical test command:

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`

Typical material index build command pattern:

- `.\.venv\Scripts\python.exe scripts\build_material_text_index.py --resource-index data/local/resource_index.json --output data/local/material_text_index.json --chunk-output data/local/material_chunk_index.json --moocs-collect-db "%APPDATA%\me.yu7400ki.moocs-collect\db.sqlite" --moocs-collect-root "%APPDATA%\me.yu7400ki.moocs-collect" --search-index "%APPDATA%\me.yu7400ki.moocs-collect\search_index" --include-moocs-collect --include-moocs-collect-search-index`

If exact PowerShell syntax is needed, prefer using `$env:APPDATA` in command examples.

## Backend / demo caution

Some demo scripts may require the FastAPI backend to be running.

If needed, use a separate terminal and set:

- `$env:PYTHONPATH = "backend"`
- `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`

Then run demo scripts from another terminal.

If backend is not needed for a specific MCP smoke test, document that clearly.

## Final behavior expectation

Act like a careful local development agent.

Prefer:

- small commits
- reproducible commands
- explicit cautions
- source/provenance preservation
- demo stability
- clean handoff docs

Avoid:

- broad rewrites
- private data commits
- overclaiming
- large raw output dumps
- unbounded crawling
- risky default-on OCR or browser automation