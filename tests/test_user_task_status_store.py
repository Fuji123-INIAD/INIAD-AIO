from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.core.user_task_status import UserTaskStatus
from backend.app.core.user_task_status_store import (
    load_user_task_statuses,
    save_user_task_statuses,
)


class UserTaskStatusStoreTests(unittest.TestCase):
    def test_missing_file_loads_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "user_task_status.json"

            statuses, warnings = load_user_task_statuses(path)

            self.assertEqual({}, statuses)
            self.assertEqual([], warnings)

    def test_save_and_load_status_dict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "local" / "user_task_status.json"
            save_user_task_statuses(
                path,
                {
                    "course-rule:COT101": UserTaskStatus(
                        task_id="course-rule:COT101",
                        status="done",
                    )
                },
            )

            statuses, warnings = load_user_task_statuses(path)

            self.assertEqual([], warnings)
            self.assertEqual("done", statuses["course-rule:COT101"].status)

    def test_corrupt_json_falls_back_to_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "user_task_status.json"
            path.write_text("{bad json", encoding="utf-8")

            statuses, warnings = load_user_task_statuses(path)

            self.assertEqual({}, statuses)
            self.assertEqual(1, len(warnings))

    def test_invalid_status_entries_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "user_task_status.json"
            path.write_text(
                '{"course-rule:COT101": "done", "course-rule:SEM101": "open"}',
                encoding="utf-8",
            )

            statuses, warnings = load_user_task_statuses(path)

            self.assertEqual(["course-rule:COT101"], list(statuses))
            self.assertEqual("done", statuses["course-rule:COT101"].status)
            self.assertEqual(1, len(warnings))


if __name__ == "__main__":
    unittest.main()
