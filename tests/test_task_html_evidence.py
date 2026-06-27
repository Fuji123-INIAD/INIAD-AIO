from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.core.task_html_evidence import load_html_evidence_by_course


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "moocs_course_details_minimal.json"


class TaskHtmlEvidenceTests(unittest.TestCase):
    def test_loads_task_related_html_evidence_from_course_details_json(self) -> None:
        evidence_by_course, warnings = load_html_evidence_by_course(
            ["COT101"],
            FIXTURE_PATH,
        )

        self.assertEqual([], warnings)
        evidence = evidence_by_course["COT101"]
        self.assertTrue(evidence)
        self.assertEqual("html", evidence[0].type)
        self.assertIn("assignment", evidence[0].source)
        self.assertIn(evidence[0].confidence, {"low", "medium", "high"})

    def test_missing_file_returns_no_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.json"

            evidence_by_course, warnings = load_html_evidence_by_course(
                ["COT101"],
                path,
            )

            self.assertEqual({}, evidence_by_course)
            self.assertEqual([], warnings)

    def test_unrelated_course_returns_no_evidence(self) -> None:
        evidence_by_course, warnings = load_html_evidence_by_course(
            ["SEM101"],
            FIXTURE_PATH,
        )

        self.assertEqual({}, evidence_by_course)
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
