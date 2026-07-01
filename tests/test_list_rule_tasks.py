from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.list_rule_tasks import build_report


FIXTURE_PATH = "tests/fixtures/moocs_course_details_minimal.json"


class ListRuleTasksTests(unittest.TestCase):
    def test_cot101_outputs_one_item(self) -> None:
        report = build_report(["COT101"], html_evidence_path=None)

        self.assertEqual(["COT101"], report["course_codes"])
        self.assertEqual(1, report["task_count"])
        self.assertEqual(1, report["active_count"])
        self.assertEqual([], report["warnings"])
        self.assertEqual("course-rule:COT101", report["items"][0]["task_id"])
        self.assertEqual("COT101", report["items"][0]["course_code"])
        self.assertEqual("COT101 課題", report["items"][0]["title"])

    def test_initial_courses_output_three_items(self) -> None:
        report = build_report(["COT101", "SEM101", "COT105"], html_evidence_path=None)

        self.assertEqual(["COT101", "SEM101", "COT105"], report["course_codes"])
        self.assertEqual(3, report["task_count"])
        self.assertEqual(3, report["active_count"])
        self.assertEqual(
            ["COT101", "SEM101", "COT105"],
            [item["course_code"] for item in report["items"]],
        )

    def test_unknown_course_does_not_fail(self) -> None:
        report = build_report(["UNKNOWN101"], html_evidence_path=None)

        self.assertEqual(["UNKNOWN101"], report["course_codes"])
        self.assertEqual(0, report["task_count"])
        self.assertEqual(0, report["active_count"])
        self.assertEqual([], report["items"])
        self.assertEqual("UNKNOWN101", report["warnings"][0]["course_code"])

    def test_active_count_is_todo_count(self) -> None:
        report = build_report(["COT101", "UNKNOWN101"], html_evidence_path=None)

        self.assertEqual(1, report["task_count"])
        self.assertEqual(1, report["active_count"])
        self.assertEqual("todo", report["items"][0]["status"])
        self.assertTrue(report["items"][0]["active"])

    def test_json_shape_is_stable_and_extended(self) -> None:
        report = build_report(["COT101"], html_evidence_path=None)

        self.assertEqual(
            ["course_codes", "task_count", "active_count", "items", "warnings"],
            list(report),
        )
        self.assertEqual(
            [
                "task_id",
                "course_code",
                "title",
                "source",
                "status",
                "active",
                "deadline_rule",
                "submission_channel",
                "confidence",
                "description",
                "deadline_note",
                "submission_note",
                "caution_note",
                "display_course_name",
                "short_name",
                "track",
                "evidence",
                "evidence_omitted_count",
                "primary_action_label",
                "primary_action_url",
                "evidence_detail_url",
            ],
            list(report["items"][0]),
        )

    def test_display_fields_are_present(self) -> None:
        report = build_report(["COT101"], html_evidence_path=None)
        item = report["items"][0]

        self.assertEqual("COT101", item["course_code"])
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item["display_course_name"])
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item["short_name"])
        self.assertEqual("COT", item["track"])
        self.assertIn("確認", item["description"])
        self.assertIn("締切", item["deadline_note"])
        self.assertIn("提出", item["submission_note"])
        self.assertTrue(item["caution_note"])

    def test_course_rule_evidence_is_present(self) -> None:
        report = build_report(["COT101"], html_evidence_path=None)
        evidence = report["items"][0]["evidence"]

        self.assertEqual(1, len(evidence))
        self.assertEqual("course_rule", evidence[0]["type"])
        self.assertEqual("COT101 course rule", evidence[0]["label"])
        self.assertEqual("medium", evidence[0]["confidence"])
        self.assertNotIn("source", evidence[0])
        self.assertEqual(
            "/api/tasks/course-rule:COT101/evidence",
            report["items"][0]["evidence_detail_url"],
        )
        self.assertEqual(0, report["items"][0]["evidence_omitted_count"])

    def test_html_evidence_can_be_attached_from_fixture_json(self) -> None:
        report = build_report(["COT101"], html_evidence_path=Path(FIXTURE_PATH))
        evidence = report["items"][0]["evidence"]

        self.assertEqual("course_rule", evidence[0]["type"])
        self.assertTrue(any(item["type"] == "html" for item in evidence))

    def test_slides_evidence_can_be_attached_from_fixture_json(self) -> None:
        report = build_report(["COT101"], html_evidence_path=Path(FIXTURE_PATH))
        evidence = report["items"][0]["evidence"]

        self.assertTrue(any(item["type"] == "slides" for item in evidence))

    def test_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/list_rule_tasks.py",
                "COT101",
                "SEM101",
                "COT105",
            ],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )

        report = json.loads(completed.stdout)

        self.assertEqual(3, report["task_count"])
        self.assertEqual(3, report["active_count"])
        self.assertEqual("COT", report["items"][0]["track"])
        self.assertEqual("course_rule", report["items"][0]["evidence"][0]["type"])


if __name__ == "__main__":
    unittest.main()
