"""Inspect v0.3 task classification against an existing MOOCs detail JSON."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.moocs_sync.sync_service import import_moocs_course_details
from backend.app.core.tasks.task_service import list_active_tasks
from backend.app.db.local_db import get_connection


DEFAULT_SOURCE = ROOT_DIR / "data" / "probe" / "moocs_course_details.json"
DISPLAY_BUCKETS = ("unknown_deadline", "review_or_feedback", "weak_candidate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import real MOOCs JSON into a temporary DB and inspect task kinds."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--now",
        help="ISO timestamp used by list_active_tasks; defaults to the current UTC time.",
    )
    return parser.parse_args()


def load_task_reasons(db_path: Path) -> dict[str, str | None]:
    """Read classification reasons without changing the task service response."""
    reasons: dict[str, str | None] = {}
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT id, raw_json FROM tasks").fetchall()

    for task_id, raw_json in rows:
        reason = None
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except json.JSONDecodeError:
            raw = None
        if isinstance(raw, dict):
            meta = raw.get("_aio_task_meta")
            if isinstance(meta, dict) and isinstance(meta.get("reason"), str):
                reason = meta["reason"]
        reasons[str(task_id)] = reason
    return reasons


def task_for_display(
    task: dict[str, Any],
    reasons: dict[str, str | None],
) -> dict[str, Any]:
    result = {
        "title": task.get("title"),
        "course_id": task.get("course_id"),
        "deadline_at": task.get("deadline_at"),
        "kind": task.get("kind"),
    }
    if task.get("moocs_url"):
        result["moocs_url"] = task["moocs_url"]
    reason = reasons.get(str(task.get("id")))
    if reason:
        result["reason"] = reason
    return result


def print_section(
    name: str,
    tasks: list[dict[str, Any]],
    reasons: dict[str, str | None],
    limit: int,
) -> None:
    shown = tasks[:limit]
    print(f"\n{name}: {len(tasks)} (showing {len(shown)})")
    print(
        json.dumps(
            [task_for_display(task, reasons) for task in shown],
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"MOOCs detail JSON not found: {source}")
    if args.limit < 0:
        raise ValueError("--limit must be zero or greater")

    now = args.now or datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="iniad_aio_task_inspect_") as temp_dir:
        db_path = Path(temp_dir) / "inspect.db"
        imported = import_moocs_course_details(source, db_path=db_path, now=now)
        result = list_active_tasks(db_path=db_path, now=now)
        reasons = load_task_reasons(db_path)

        print(f"source: {source}")
        print(f"now: {now}")
        print(f"import_counts: {json.dumps(imported['counts'], ensure_ascii=False)}")
        print(f"summary: {json.dumps(result['summary'], ensure_ascii=False)}")
        print(f"upcoming: {len(result['upcoming'])}")
        for bucket in DISPLAY_BUCKETS:
            print_section(bucket, result[bucket], reasons, args.limit)


if __name__ == "__main__":
    main()
