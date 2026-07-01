from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import backend.main as backend_main
from backend.main import app


class TaskListApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        backend_main.USER_TASK_STATUS_PATH = (
            Path(self.temp_dir.name) / "user_task_status.json"
        )
        backend_main.HTML_EVIDENCE_PATH = Path(self.temp_dir.name) / "missing.json"
        backend_main.MOOCS_COLLECT_DB_PATH = None
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False
        self.client = TestClient(app)

    def test_cot101_returns_one_rule_task(self) -> None:
        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(["COT101"], data["course_codes"])
        self.assertEqual(1, data["task_count"])
        self.assertEqual(1, data["active_count"])
        self.assertEqual([], data["warnings"])
        self.assertEqual(1, len(data["items"]))
        self.assertEqual("course-rule:COT101", data["items"][0]["id"])
        self.assertEqual("course-rule:COT101", data["items"][0]["task_id"])
        self.assertEqual("COT101", data["items"][0]["course_code"])
        self.assertIn("primary_action_label", data["items"][0])
        self.assertIn("primary_action_url", data["items"][0])

    def test_multiple_course_codes_return_three_rule_tasks(self) -> None:
        response = self.client.get(
            "/api/tasks",
            params=[
                ("course_code", "COT101"),
                ("course_code", "SEM101"),
                ("course_code", "COT105"),
            ],
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(3, data["task_count"])
        self.assertEqual(3, data["active_count"])
        self.assertEqual(
            ["COT101", "SEM101", "COT105"],
            [item["course_code"] for item in data["items"]],
        )

    def test_unknown_course_goes_to_warnings(self) -> None:
        response = self.client.get(
            "/api/tasks",
            params=[("course_code", "UNKNOWN101")],
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(0, data["task_count"])
        self.assertEqual(0, data["active_count"])
        self.assertEqual([], data["items"])
        self.assertEqual("UNKNOWN101", data["warnings"][0]["course_code"])

    def test_items_include_phase_3_17_display_fields(self) -> None:
        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        item = response.json()["items"][0]
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item["display_course_name"])
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item["short_name"])
        self.assertEqual("COT", item["track"])
        self.assertEqual("todo", item["status"])
        self.assertTrue(item["active"])
        self.assertIn("確認", item["description"])
        self.assertIn("締切", item["deadline_note"])
        self.assertIn("提出", item["submission_note"])
        self.assertTrue(item["caution_note"])

    def test_items_include_course_rule_evidence(self) -> None:
        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        evidence = response.json()["items"][0]["evidence"]
        self.assertEqual(1, len(evidence))
        self.assertEqual("course_rule", evidence[0]["type"])
        self.assertEqual("COT101 course rule", evidence[0]["label"])
        self.assertEqual("medium", evidence[0]["confidence"])
        self.assertNotIn("source", evidence[0])
        self.assertEqual(
            "/api/tasks/course-rule:COT101/evidence",
            response.json()["items"][0]["evidence_detail_url"],
        )
        self.assertEqual(0, response.json()["items"][0]["evidence_omitted_count"])
        self.assertIsNone(response.json()["items"][0]["primary_action_label"])
        self.assertIsNone(response.json()["items"][0]["primary_action_url"])

    def test_items_can_include_html_evidence_from_json(self) -> None:
        backend_main.HTML_EVIDENCE_PATH = (
            Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"
        )

        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        evidence = response.json()["items"][0]["evidence"]
        self.assertEqual("course_rule", evidence[0]["type"])
        self.assertTrue(any(item["type"] == "html" for item in evidence))
        item = response.json()["items"][0]
        self.assertTrue(item["primary_action_label"])
        self.assertEqual(
            "https://moocs.iniad.org/courses/2026/COT101/01-1/assignment",
            item["primary_action_url"],
        )

    def test_items_can_include_slides_evidence_from_json(self) -> None:
        backend_main.HTML_EVIDENCE_PATH = (
            Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"
        )

        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        evidence = response.json()["items"][0]["evidence"]
        slides = [item for item in evidence if item["type"] == "slides"]
        self.assertTrue(slides)
        self.assertEqual("high", slides[0]["confidence"])
        self.assertNotIn("source", slides[0])

    def test_task_evidence_detail_api_includes_full_sources(self) -> None:
        backend_main.HTML_EVIDENCE_PATH = (
            Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"
        )

        response = self.client.get("/api/tasks/course-rule:COT101/evidence")

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("course-rule:COT101", data["task_id"])
        evidence = data["evidence"]
        self.assertTrue(any(item["type"] == "slides" for item in evidence))
        self.assertTrue(all("source" in item for item in evidence))

    def test_unknown_task_evidence_detail_returns_404(self) -> None:
        response = self.client.get("/api/tasks/unknown/evidence")

        self.assertEqual(404, response.status_code)

    def test_patch_status_updates_task_list_response(self) -> None:
        update_response = self.client.patch(
            "/api/tasks/course-rule:COT101/status",
            json={"status": "done"},
        )

        self.assertEqual(200, update_response.status_code)
        self.assertEqual("done", update_response.json()["status"])

        list_response = self.client.get(
            "/api/tasks",
            params=[("course_code", "COT101")],
        )
        item = list_response.json()["items"][0]
        self.assertEqual("done", item["status"])
        self.assertFalse(item["active"])
        self.assertEqual(0, list_response.json()["active_count"])
        self.assertIn('"course-rule:COT101": "done"', backend_main.USER_TASK_STATUS_PATH.read_text(encoding="utf-8"))

    def test_patch_status_can_mark_ignored_and_todo(self) -> None:
        ignored_response = self.client.patch(
            "/api/tasks/course-rule:COT101/status",
            json={"status": "ignored"},
        )
        self.assertEqual(200, ignored_response.status_code)
        self.assertEqual("ignored", ignored_response.json()["status"])

        todo_response = self.client.patch(
            "/api/tasks/course-rule:COT101/status",
            json={"status": "todo"},
        )
        self.assertEqual(200, todo_response.status_code)
        self.assertEqual("todo", todo_response.json()["status"])

        list_response = self.client.get(
            "/api/tasks",
            params=[("course_code", "COT101")],
        )
        item = list_response.json()["items"][0]
        self.assertEqual("todo", item["status"])
        self.assertTrue(item["active"])

    def test_patch_invalid_status_returns_400(self) -> None:
        response = self.client.patch(
            "/api/tasks/course-rule:COT101/status",
            json={"status": "open"},
        )

        self.assertEqual(400, response.status_code)

    def test_saved_status_is_loaded_on_next_access(self) -> None:
        backend_main.USER_TASK_STATUS_PATH.write_text(
            '{"course-rule:COT101": "done"}',
            encoding="utf-8",
        )
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_LOADED = False

        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        item = response.json()["items"][0]
        self.assertEqual("done", item["status"])
        self.assertFalse(item["active"])

    def test_corrupt_status_json_does_not_break_task_list(self) -> None:
        backend_main.USER_TASK_STATUS_PATH.write_text("{bad json", encoding="utf-8")
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False

        response = self.client.get("/api/tasks", params=[("course_code", "COT101")])

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("todo", data["items"][0]["status"])
        self.assertTrue(data["warnings"])


if __name__ == "__main__":
    unittest.main()
