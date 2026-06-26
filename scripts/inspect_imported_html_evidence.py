"""Import a sample MOOCs detail JSON and inspect HTML evidence task metadata."""

from __future__ import annotations

import argparse
import json
import sqlite3
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


DEFAULT_SOURCE = ROOT_DIR / "data" / "probe" / "moocs_course_details_sample.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import sample MOOCs JSON into a temporary DB and show HTML evidence task meta."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--now",
        help="ISO timestamp used by import/listing; defaults to the current UTC time.",
    )
    return parser.parse_args()


def load_tasks_for_display(db_path: Path, limit: int) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT title, deadline_at, moocs_url, raw_json
            FROM tasks
            ORDER BY title, id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    tasks: list[dict[str, Any]] = []
    for row in rows:
        try:
            raw_json = json.loads(row["raw_json"])
        except (TypeError, json.JSONDecodeError):
            raw_json = {}
        meta = raw_json.get("_aio_task_meta") if isinstance(raw_json, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        tasks.append(
            {
                "task_title": row["title"],
                "kind": meta.get("kind"),
                "deadline_text_candidates": meta.get("deadline_text_candidates"),
                "deadline_source_candidate": meta.get("deadline_source_candidate"),
                "submit_channel_candidate": meta.get("submit_channel_candidate"),
                "submit_channel_confidence": meta.get("submit_channel_confidence"),
                "accepting_status_text": meta.get("accepting_status_text"),
                "html_keyword_contexts": meta.get("html_keyword_contexts"),
                "content_retrieval_method": meta.get("content_retrieval_method"),
                "content_fetched_at": meta.get("content_fetched_at"),
                "signin_redirect": meta.get("signin_redirect"),
                "deadline_at": row["deadline_at"],
                "moocs_url": row["moocs_url"],
            }
        )
    return tasks


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"MOOCs sample detail JSON not found: {source}")
    if args.limit < 0:
        raise ValueError("--limit must be zero or greater")

    now = args.now or datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="iniad_aio_html_evidence_") as temp_dir:
        db_path = Path(temp_dir) / "inspect.db"
        imported = import_moocs_course_details(source, db_path=db_path, now=now)
        active = list_active_tasks(db_path=db_path, now=now)
        tasks = load_tasks_for_display(db_path, args.limit)

        print(
            json.dumps(
                {
                    "source": str(source),
                    "temporary_db": str(db_path),
                    "now": now,
                    "import_counts": imported["counts"],
                    "active_summary": active["summary"],
                    "active_bucket_counts": {
                        "upcoming": len(active["upcoming"]),
                        "unknown_deadline": len(active["unknown_deadline"]),
                        "review_or_feedback": len(active["review_or_feedback"]),
                        "weak_candidate": len(active["weak_candidate"]),
                    },
                    "tasks": tasks,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
