from __future__ import annotations

import json
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


FRONTEND_INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


class V03SmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        backend_main.USER_TASK_STATUS_PATH = (
            Path(self.temp_dir.name) / "local" / "user_task_status.json"
        )
        backend_main.HTML_EVIDENCE_PATH = Path(self.temp_dir.name) / "missing.json"
        backend_main.MOOCS_COLLECT_DB_PATH = None
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False
        self.client = TestClient(app)

    def test_v03_task_flow_smoke(self) -> None:
        task_params = [
            ("course_code", "COT101"),
            ("course_code", "SEM101"),
            ("course_code", "COT105"),
        ]

        list_response = self.client.get("/api/tasks", params=task_params)

        self.assertEqual(200, list_response.status_code)
        list_data = list_response.json()
        self.assertEqual(["COT101", "SEM101", "COT105"], list_data["course_codes"])
        self.assertEqual(3, list_data["task_count"])
        self.assertEqual(3, list_data["active_count"])
        self.assertEqual(
            ["COT101", "SEM101", "COT105"],
            [item["course_code"] for item in list_data["items"]],
        )

        task_id = "course-rule:COT101"
        patch_response = self.client.patch(
            f"/api/tasks/{task_id}/status",
            json={"status": "done"},
        )

        self.assertEqual(200, patch_response.status_code)
        self.assertEqual("done", patch_response.json()["status"])

        updated_response = self.client.get("/api/tasks", params=task_params)

        self.assertEqual(200, updated_response.status_code)
        updated_items = updated_response.json()["items"]
        cot101 = next(item for item in updated_items if item["task_id"] == task_id)
        self.assertEqual("done", cot101["status"])
        self.assertFalse(cot101["active"])
        self.assertEqual(2, updated_response.json()["active_count"])

        saved_statuses = json.loads(
            backend_main.USER_TASK_STATUS_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual("done", saved_statuses[task_id])

        evidence_response = self.client.get(cot101["evidence_detail_url"])

        self.assertEqual(200, evidence_response.status_code)
        evidence_data = evidence_response.json()
        self.assertEqual(task_id, evidence_data["task_id"])
        self.assertTrue(evidence_data["evidence"])
        self.assertTrue(all("source" in item for item in evidence_data["evidence"]))

    def test_frontend_references_v03_task_apis(self) -> None:
        html = FRONTEND_INDEX.read_text(encoding="utf-8")

        self.assertIn('fetch("/api/tasks?" + ruleTaskQuery)', html)
        self.assertIn(
            "course_code=COT101&course_code=SEM101&course_code=COT105",
            html,
        )
        self.assertIn(
            'fetch("/api/tasks/" + encodeURIComponent(taskId) + "/status"',
            html,
        )
        self.assertIn("loadTaskEvidenceDetails(task.evidence_detail_url", html)
        self.assertIn("fetch(url)", html)


if __name__ == "__main__":
    unittest.main()
