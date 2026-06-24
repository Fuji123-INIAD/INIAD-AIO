from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.core.moocs_sync.importer import (
    load_course_details_json,
    normalize_course_details,
    normalize_source_key,
    stable_id,
)
from backend.app.core.moocs_sync.sync_service import (
    import_moocs_course_details,
    import_moocs_course_details_data,
)
from backend.app.core.tasks.task_service import list_active_tasks, set_task_status


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"
TABLES = ("courses", "lectures", "pages", "materials", "tasks")


class MoocsImporterTests(unittest.TestCase):
    def test_normalization_builds_stable_ids_and_fallback_keys(self) -> None:
        data = load_course_details_json(FIXTURE_PATH)
        first = normalize_course_details(data, now="2026-06-24T00:00:00+00:00")
        second = normalize_course_details(data, now="2026-06-25T00:00:00+00:00")

        for table in TABLES:
            self.assertEqual(
                [record["id"] for record in first[table]],
                [record["id"] for record in second[table]],
            )
        self.assertEqual(
            stable_id("course", "https://moocs.iniad.org/courses/2026/COT101"),
            first["courses"][0]["id"],
        )
        self.assertEqual("COT101", first["courses"][0]["course_code"])
        self.assertEqual(2026, first["courses"][0]["year"])

        fallback_data = {
            "course_title": "URLなし科目",
            "lessons": [{"lesson_title": "講義", "pages": [{"page_title": "資料"}]}],
        }
        fallback = normalize_course_details(fallback_data)
        self.assertTrue(fallback["courses"][0]["source_key"].startswith("fallback:"))
        self.assertTrue(fallback["lectures"][0]["source_key"].startswith("fallback:"))
        self.assertTrue(fallback["pages"][0]["source_key"].startswith("fallback:"))

    def test_source_key_url_normalization(self) -> None:
        self.assertEqual(
            "https://moocs.iniad.org/courses/2026/COT101",
            normalize_source_key(
                "HTTPS://MOOCS.INIAD.ORG/courses/2026/COT101/#section"
            ),
        )

    def test_import_is_idempotent_and_preserves_user_task_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "local.db"
            first = import_moocs_course_details(
                FIXTURE_PATH,
                db_path=db_path,
                now="2026-06-24T00:00:00+00:00",
            )
            self.assertEqual(
                {"courses": 1, "lectures": 2, "pages": 3, "materials": 2, "tasks": 2},
                first["counts"],
            )

            with closing(sqlite3.connect(db_path)) as connection:
                counts_after_first = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in TABLES
                }
                task_id, first_seen = connection.execute(
                    "SELECT id, first_seen_at FROM tasks ORDER BY id LIMIT 1"
                ).fetchone()

            active = list_active_tasks(db_path=db_path, now="2026-06-24T00:00:00+00:00")
            self.assertEqual(2, len(active["unknown_deadline"]))
            set_task_status(task_id, "done", db_path=db_path)

            second = import_moocs_course_details(
                FIXTURE_PATH,
                db_path=db_path,
                now="2026-06-25T00:00:00+00:00",
            )
            self.assertEqual(first["counts"], second["counts"])

            with closing(sqlite3.connect(db_path)) as connection:
                counts_after_second = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in TABLES
                }
                status = connection.execute(
                    "SELECT status FROM user_task_status WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
                task_times = connection.execute(
                    "SELECT first_seen_at, last_seen_at, updated_at FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()
                sync_runs = connection.execute(
                    "SELECT status, detail_json FROM sync_runs ORDER BY started_at"
                ).fetchall()

            self.assertEqual(counts_after_first, counts_after_second)
            self.assertEqual("done", status)
            self.assertEqual(first_seen, task_times[0])
            self.assertEqual("2026-06-25T00:00:00+00:00", task_times[1])
            self.assertEqual("2026-06-25T00:00:00+00:00", task_times[2])
            self.assertEqual(["ok", "ok"], [row[0] for row in sync_runs])
            self.assertEqual(first["counts"], json.loads(sync_runs[0][1]))

    def test_data_entry_point_and_error_sync_run(self) -> None:
        data = load_course_details_json(FIXTURE_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "local.db"
            result = import_moocs_course_details_data(data, db_path=db_path)
            self.assertEqual("ok", result["status"])

            with self.assertRaises(ValueError):
                import_moocs_course_details_data([], db_path=db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                error_run = connection.execute(
                    "SELECT status, detail_json FROM sync_runs WHERE status = 'error'"
                ).fetchone()
            self.assertIsNotNone(error_run)
            self.assertIn("error", json.loads(error_run[1]))


if __name__ == "__main__":
    unittest.main()
