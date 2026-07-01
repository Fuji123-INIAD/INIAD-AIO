# Local Resource Index

INIAD-AIO v0.3 MCP preparation Batch 2 defines a local resource index for MOOCs-Collect artifacts. The index lets AIO recognize locally saved lecture resources, especially PDFs, before later phases add PDF text extraction, search APIs, and MCP tools.

## Goals

- Discover MOOCs-Collect PDFs from a local filesystem root.
- Register each PDF as a lecture material resource.
- Keep resources even when `course_code` cannot be inferred, so non-first-year or future courses are not lost.
- Infer `course_title` and `lecture_title` from local paths for later PDF extraction and search.
- Write `data/local/resource_index.json` as runtime local data for later MCP handoff.
- Avoid reading PDF body text in this phase.

## Non-Goals

- PDF text extraction.
- OCR.
- MCP server or MCP tool implementation.
- FastAPI API additions.
- DB schema, importer, task list, or deadline calculation changes.

## Resource Model

Each resource entry has the following fields:

| Field | Type | Notes |
| --- | --- | --- |
| `resource_id` | string | Stable identifier derived from the normalized `local_path`. |
| `course_code` | string or null | Best-effort inference from path or filename. Unknown courses remain indexed as `null`. |
| `course_title` | string or null | Best-effort title inferred from the root-relative path. |
| `lecture_key` | string or null | Best-effort inference such as `11-1`, `00-3`, `01`, or `02`. |
| `lecture_title` | string or null | Best-effort title inferred from the lecture folder. |
| `title` | string | Display title. For discovered PDFs this is the filename. |
| `resource_type` | string | One of `pdf`, `slides`, `html`, or `unknown`. Batch 2 emits `pdf`. |
| `source_url` | string or null | Original web source when known. Filesystem discovery leaves this `null`. |
| `local_path` | string | Absolute local path to the resource. |
| `page_key` | string or null | MOOCs page key when known. Filesystem discovery leaves this `null`. |
| `text_available` | boolean | Whether extracted text is available. Batch 2 sets `false`. |
| `text_cache_path` | string or null | Local extracted-text cache path. Batch 2 leaves this `null`. |
| `discovered_from` | string | Discovery source, such as `filesystem`. |
| `warnings` | array | Resource-level warning objects. |

Index shape:

```json
{
  "resources": [
    {
      "resource_id": "local-resource:...",
      "course_code": "COT101",
      "course_title": "Computer Science",
      "lecture_key": "11-1",
      "lecture_title": null,
      "title": "example.pdf",
      "resource_type": "pdf",
      "source_url": null,
      "local_path": "...",
      "page_key": null,
      "text_available": false,
      "text_cache_path": null,
      "discovered_from": "filesystem",
      "warnings": []
    }
  ],
  "warnings": []
}
```

## Discovery Rules

Batch 2 scans the configured root recursively and registers files whose extension is `.pdf`, case-insensitively.

`course_code` is inferred from path components or filename using a loose course-like pattern rather than a COT-only allowlist. The current implementation recognizes codes shaped like letters followed by digits, for example `COT101`, `SEM101`, `COT105`, and likely future variants such as `INFO1001`. If no course code can be inferred, the resource remains in the index with `course_code: null`.

`course_title` is inferred from the root-relative path:

- If the scan root is a year folder such as `2026`, the first child folder is treated as the course title.
- If the scan root contains a year folder such as `moocs-collect/2026/...`, the folder after the year is treated as the course title.
- If the scan root is a specific course folder, the root folder name is treated as the course title.

For example, scanning `...\moocs-collect\2026` over:

```text
情報連携学概論 I\08_ セキュリティ\Part1.pdf
```

produces `course_title: "情報連携学概論 I"`.

`lecture_key` and `lecture_title` are inferred from the lecture folder when possible:

- `08_ セキュリティ` becomes `lecture_key: "08"` and `lecture_title: "セキュリティ"`.
- `AI-05_ 回帰の復習` becomes `lecture_key: "05"` and `lecture_title: "回帰の復習"`.
- `DS-00_ データ解析のための環境構築` becomes `lecture_key: "00"` and `lecture_title: "データ解析のための環境構築"`.

If the lecture folder does not contain a title, `lecture_key` still falls back to a lecture-like token such as `11-1`, `00-3`, `01`, or `02`, and `lecture_title` remains `null`.

If no course code can be inferred but `course_title` is present, the resource is still valid and remains in the index.

`resource_id` is generated from the normalized local path. Re-running the index builder against the same file produces the same ID.

## CLI

Example:

```powershell
.\.venv\Scripts\python.exe scripts/build_local_resource_index.py `
  --root "$env:APPDATA\me.yu7400ki.moocs-collect" `
  --output data/local/resource_index.json
```

If the root does not exist, the command still writes a valid index with an empty `resources` array and a warning.

## Copyright And Distribution Notes

- PDF bodies, slide bodies, and extracted text are user-local study materials.
- AIO must not upload PDF bodies, slide bodies, extracted text caches, or MOOCs-Collect local artifacts to GitHub or a shared server.
- `data/local/` is runtime local data and is ignored by Git.
- `resource_index.json` can contain private local paths. Treat it as local runtime state, not as a distributable artifact.
- Later MCP tools should read local resources from the user's machine and avoid copying copyrighted course content into remote logs, repositories, or hosted services.
