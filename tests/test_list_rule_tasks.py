from __future__ import annotations

import json
import subprocess
import sys
import unittest

from scripts.list_rule_tasks import build_report


class ListRuleTasksTests(unittest.TestCase):
    def test_cot101_outputs_one_item(self) -> None:
        report = build_report(["COT101"])

        self.assertEqual(["COT101"], report["course_codes"])
        self.assertEqual(1, report["task_count"])
        self.assertEqual(1, report["active_count"])
        self.assertEqual([], report["warnings"])
        self.assertEqual("course-rule:COT101", report["items"][0]["task_id"])
        self.assertEqual("COT101 課題", report["items"][0]["title"])

    def test_initial_courses_output_three_items(self) -> None:
        report = build_report(["COT101", "SEM101", "COT105"])

        self.assertEqual(["COT101", "SEM101", "COT105"], report["course_codes"])
        self.assertEqual(3, report["task_count"])
        self.assertEqual(3, report["active_count"])
        self.assertEqual(
            ["COT101", "SEM101", "COT105"],
            [item["course_code"] for item in report["items"]],
        )

    def test_unknown_course_does_not_fail(self) -> None:
        report = build_report(["UNKNOWN101"])

        self.assertEqual(["UNKNOWN101"], report["course_codes"])
        self.assertEqual(0, report["task_count"])
        self.assertEqual(0, report["active_count"])
        self.assertEqual([], report["items"])
        self.assertEqual("UNKNOWN101", report["warnings"][0]["course_code"])

    def test_active_count_is_todo_count(self) -> None:
        report = build_report(["COT101", "UNKNOWN101"])

        self.assertEqual(1, report["task_count"])
        self.assertEqual(1, report["active_count"])
        self.assertEqual("todo", report["items"][0]["status"])
        self.assertTrue(report["items"][0]["active"])

    def test_json_shape_is_stable(self) -> None:
        report = build_report(["COT101"])

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
            ],
            list(report["items"][0]),
        )

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


if __name__ == "__main__":
    unittest.main()
