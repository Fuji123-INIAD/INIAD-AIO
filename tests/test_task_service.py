from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.core.tasks.task_service import list_active_tasks
from backend.app.db.local_db import get_connection, init_db


NOW = "2026-06-24T12:00:00+00:00"


class TaskServiceClassificationTests(unittest.TestCase):
    def test_groups_kinds_and_filters_status_and_past_deadlines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "local.db"
            init_db(db_path)
            self._insert_records(db_path)

            result = list_active_tasks(db_path=db_path, now=NOW)

            self.assertEqual(["submission-future"], self._ids(result["upcoming"]))
            self.assertEqual(["legacy-unknown"], self._ids(result["unknown_deadline"]))
            self.assertEqual(["review-future"], self._ids(result["review_or_feedback"]))
            self.assertEqual(["weak-unknown"], self._ids(result["weak_candidate"]))
            self.assertEqual(
                {
                    "submission": 2,
                    "review_or_feedback": 1,
                    "weak_candidate": 1,
                },
                result["summary"],
            )
            self.assertEqual("submission", result["unknown_deadline"][0]["kind"])
            self.assertEqual(
                "review_or_feedback", result["review_or_feedback"][0]["kind"]
            )
            self.assertEqual("weak_candidate", result["weak_candidate"][0]["kind"])

    @staticmethod
    def _ids(tasks: list[dict[str, object]]) -> list[str]:
        return [str(task["id"]) for task in tasks]

    @staticmethod
    def _insert_records(db_path: Path) -> None:
        timestamp = "2026-06-01T00:00:00+00:00"
        tasks = [
            ("submission-future", "submission", "2026-07-01T00:00:00+00:00", None),
            ("legacy-unknown", None, None, None),
            ("review-future", "review_or_feedback", "2026-07-02T00:00:00+00:00", None),
            ("weak-unknown", "weak_candidate", None, None),
            ("submission-past", "submission", "2026-05-01T00:00:00+00:00", None),
            ("review-past", "review_or_feedback", "2026-05-02T00:00:00+00:00", None),
            ("review-done", "review_or_feedback", None, "done"),
            ("weak-ignored", "weak_candidate", None, "ignored"),
        ]

        with closing(get_connection(db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO courses (
                        id, title, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("course:test", "Test Course", "moocs", timestamp, timestamp),
                )
                for task_id, kind, deadline_at, status in tasks:
                    raw_json = {}
                    if kind is not None:
                        raw_json["_aio_task_meta"] = {
                            "kind": kind,
                            "confidence": "high",
                            "reason": "test fixture",
                        }
                    connection.execute(
                        """
                        INSERT INTO tasks (
                            id, course_id, title, deadline_at, raw_json,
                            first_seen_at, last_seen_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            "course:test",
                            task_id,
                            deadline_at,
                            json.dumps(raw_json),
                            timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
                    if status is not None:
                        connection.execute(
                            """
                            INSERT INTO user_task_status (
                                task_id, status, updated_at
                            ) VALUES (?, ?, ?)
                            """,
                            (task_id, status, timestamp),
                        )


if __name__ == "__main__":
    unittest.main()
