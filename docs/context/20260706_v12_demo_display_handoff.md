# v1.2 Demo Display Handoff

Date: 2026-07-06
Branch: feature/v1.2-mcp-chat-materials-experiment

## Scope

- Limited the follow-up work to `scripts/demo_aio_mcp_chat_flow.py` display cleanup and fixture-only tests.
- Did not expand the MOOCs-Collect provider, MaterialText, or MaterialChunk core design.
- Did not add or commit real `data/local`, AppData, DB, PDF, search index, cookies, browser profile, credentials, or lecture body dumps.

## Changes

- Material search output is split into:
  - `Text snippets / 本文あり候補`
  - `Metadata-only fallback`
- Provider, source type, extraction method, and metadata-only state are visible in demo rows.
- Snippets are collapsed and capped to short presentation-safe previews.
- `First material snippets` prefers text-bearing chunks over metadata-only chunks.
- Demo caution explicitly says snippets may come from MOOCs-Collect `search_index` and are not guaranteed PDF text-layer extraction or complete full text.

## Verification So Far

- `.\.venv\Scripts\python.exe -m unittest tests.test_demo_aio_mcp_chat_flow`
- `.\.venv\Scripts\python.exe -m unittest tests.test_moocs_collect_v12_providers`

Both passed before this handoff file was added.

## Next Required Checks

- Run full unittest: `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Check `git status --short --untracked-files=all`
- Check `git diff --stat`
- Confirm no generated local data or sensitive files are included before commit.
