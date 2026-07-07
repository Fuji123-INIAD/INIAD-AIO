# 2026-07-07 AGENTS.md Handoff

- Current branch: `feature/v1.2-mcp-chat-materials-experiment`
- Latest commit: `7a9ca13 Add project agent instructions`
- Pushed: not yet after this local commit
- Git status at checkpoint: branch ahead of origin by 1, no working tree changes before this handoff file
- Changed files in completed task: `AGENTS.md`
- Tests run: `.\.venv\Scripts\python.exe -m unittest discover -s tests` -> 162 tests OK
- Completed: added repository-root `AGENTS.md` with project rules and committed it as a standalone task.
- Demo commands checked in this task: none; this was instructions-only setup.
- What works: repository now has local agent rules for v1.2 MCP demo work.
- What does not work / not checked yet: MCP server startup, Claude Desktop template, MCP smoke test, and demo docs still need inspection and updates.
- Next recommended task: inspect MCP server entry points and existing demo scripts, then document connection and smoke-test workflow.
- Do not commit: `data/local/*`, AppData contents, real `db.sqlite`, real `search_index`, PDFs, OCR output, cookies, `storage_state`, browser profiles, real Claude Desktop config, API keys, credentials, lecture body dumps, long raw previews, private caches, or private indexes.
