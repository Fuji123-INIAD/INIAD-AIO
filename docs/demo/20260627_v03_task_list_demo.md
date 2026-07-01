# INIAD-AIO v0.3 Task List Demo Guide

This guide describes the v0.3 RC1 task list demo. The goal of RC1 is to show a human-reviewable task list and let users jump from each row to the most useful MOOCs, Slides, or evidence source when one is available.

## Scope

The task list is generated from the Course Rule Registry for known courses such as COT101, SEM101, and COT105. It does not change the DB schema, importer, or deadline calculation. Deadlines remain rule-based notes, not automatically confirmed real MOOCs deadlines.

## Run

Start the backend with Docker Compose:

```bash
docker compose up --build
```

If `backend/.env` does not exist, create it from the example:

```bash
copy .env.example backend\.env
```

The frontend is served by FastAPI at:

```text
http://localhost:8000/
```

## API

Task list:

```text
GET /api/tasks?course_code=COT101&course_code=SEM101&course_code=COT105
```

Evidence detail:

```text
GET /api/tasks/{task_id}/evidence
```

Status update:

```text
PATCH /api/tasks/{task_id}/status
```

## Table UI

The v0.3 RC1 frontend renders the rule-based tasks as a table. The table shows course, track, task description, deadline note, primary open action, status, and evidence detail controls.

The `開く` column uses the task item's `primary_action_url`. When a URL exists, it renders a link that opens in a new tab with `target="_blank"` and `rel="noopener noreferrer"`. When no primary action URL exists, the table shows `-`.

## Course Display Name

Each rule task keeps its original `course_code` and also includes display fields for the UI:

- `display_course_name`
- `short_name`
- `track`

Known courses use the configured display names. Unknown courses fall back to the course code.

## Status Persistence

The frontend status select supports:

- `todo`
- `done`
- `ignored`

Changing a status calls `PATCH /api/tasks/{task_id}/status`. The next `GET /api/tasks` response reflects the saved status and active count.

The demo status store is local JSON:

```text
data/local/user_task_status.json
```

`data/local` is local runtime data and is not intended to be committed.

## Evidence Summary And Detail

`GET /api/tasks` returns lightweight evidence summaries in `items[].evidence`:

- `type`
- `label`
- `confidence`

The list response intentionally does not include evidence `source` in each summary item. Full evidence sources remain available through `items[].evidence_detail_url`.

`GET /api/tasks/{task_id}/evidence` returns full evidence entries including `source`. This keeps the existing evidence detail API behavior intact.

## Primary Action Link

Each task item includes:

- `primary_action_label`
- `primary_action_url`

The primary action is selected from the prepared evidence list:

- URL sources only become `primary_action_url`.
- HTML evidence is preferred over Slides evidence.
- Within the same evidence type, confidence ranks `high > medium > low`.
- Non-URL sources such as `course_rule` or MOOCs-Collect page keys remain visible in evidence detail but are not used as primary action URLs.

This allows a user to click directly from the table to the most relevant MOOCs page or Slides URL when the evidence has one.

## Smoke Test

Run the v0.3 smoke test:

```bash
.\.venv\Scripts\python.exe -m unittest tests.test_v03_smoke
```

Run the full test suite:

```bash
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The smoke flow verifies that `/api/tasks` returns the COT101 / SEM101 / COT105 task list, status changes persist, evidence detail returns full sources, and the frontend references the required v0.3 task APIs and primary action UI.

## Known Limits

- Real MOOCs login and live browser analysis are outside this demo path.
- Deadline extraction is not finalized in this RC; deadline notes remain rule-based.
- `MOOCS_COLLECT_DB_PATH` is optional and read-only when configured.
- Evidence detail sources may be MOOCs URLs, Slides URLs, or local page keys; only URL sources are promoted to primary actions.
