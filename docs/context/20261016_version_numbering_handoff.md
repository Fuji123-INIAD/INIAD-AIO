# Development version numbering handoff

Date: 2026-10-16
Branch: `feature/v0.5-adventure-mcp-ontology`
Source snapshot: `850bdc7eb4cb92465afea4740c79552f078b6098` on `feature/v1.1-adventure-mcp-ontology`

- Updated pre-release demo/experiment labels: old v1.0-v1.4 -> v0.4-v0.8.
- Preserved all original commits, tags, and historical branch pointers. No rebase or force update.
- Reserved future official v1.0 roadmap meaning; see [version mapping](../versioning.md).
- Updated document names/references and the existing UI label expectation where present. API/data formats and internal identifiers are unchanged.
- Validation: latest v0.8 snapshot passed all 173 existing unit tests on 2026-10-16 using the existing local environment. Earlier snapshots receive the same label-only transformation and static review; their full suites were not separately rerun. Main changes documentation only.
- Reviewed: branch-specific file plan, source snapshots, Git diff/status, no private data or generated runtime files in the commit plan.
- Live MOOCs, Claude Desktop UI, and external APIs were not exercised; no functional change was intended.
- Follow-up: use the new branch names; keep old branch/commit links for historical references.
