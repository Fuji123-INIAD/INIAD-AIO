# INIAD-AIO v0.3 RC1 Review Note

Date: 2026-07-01

## Confirmed Features

- `/api/tasks` returns rule-based task items for COT101 / SEM101 / COT105.
- Task items include course display fields: `display_course_name`, `short_name`, and `track`.
- Task status can be changed with `PATCH /api/tasks/{task_id}/status`.
- Saved status is reflected in later `/api/tasks` responses and the active count.
- Evidence summary remains lightweight in `/api/tasks`.
- Evidence detail remains available at `/api/tasks/{task_id}/evidence` and includes full `source` values.
- Task items include `primary_action_label` and `primary_action_url`.
- The frontend table includes an `開く` column.
- The `開く` column opens the selected primary action URL in a new tab when one exists and shows `-` when no URL exists.

## Remaining Tasks

- Replace rule-only deadline notes with confirmed deadline extraction when that feature is ready.
- Move demo status persistence from JSON to the planned local DB path when the v0.3 persistence layer is finalized.
- Add broader fixture coverage for multiple HTML and Slides evidence combinations from real course exports.
- Add browser-level UI verification once the demo is prepared for visual regression checks.

## Known Constraints

- DB schema is unchanged for RC1.
- Importer behavior is unchanged for RC1.
- Deadline calculation is unchanged for RC1.
- `data/local` remains runtime-only local data and should not be committed.
- Non-URL evidence sources are kept in evidence detail but are not used as primary action URLs.
- HTML evidence is preferred over Slides evidence for the primary action, then confidence ranks `high > medium > low`.
