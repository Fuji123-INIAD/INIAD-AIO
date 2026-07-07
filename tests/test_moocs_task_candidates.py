from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.core.moocs_task_candidates import load_moocs_derived_task_prototypes


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "moocs_cot105_task_candidates_sanitized.json"
)


class MoocsTaskCandidateTests(unittest.TestCase):
    def test_loads_cot105_moocs_derived_task_with_low_confidence_deadline_text(self) -> None:
        tasks, warnings = load_moocs_derived_task_prototypes(["COT105"], FIXTURE_PATH)

        self.assertEqual([], warnings)
        self.assertEqual(1, len(tasks))
        task = tasks[0]
        self.assertTrue(task.task_id.startswith("moocs-task:COT105:"))
        self.assertEqual("COT105", task.course_code)
        self.assertEqual("moocs", task.source)
        self.assertEqual("moocs_submission", task.kind)
        self.assertEqual("high", task.confidence)
        self.assertEqual("unknown", task.deadline_rule)
        self.assertIn("MOOCs deadline text candidate", task.deadline_note)
        self.assertEqual("low", task.deadline_confidence)
        self.assertEqual("moocs", task.submission_channel)
        self.assertEqual("medium", task.submission_confidence)
        self.assertEqual("pptx or pdf", task.submission_format_text)
        self.assertEqual("medium", task.submission_format_confidence)
        self.assertEqual("moocs", task.evidence_type)
        self.assertEqual(
            "https://moocs.iniad.org/courses/2026/COT105/08/report-part1",
            task.evidence_source,
        )
        self.assertIn("公式表示", task.caution_note)

    def test_skips_courses_outside_requested_scope(self) -> None:
        tasks, warnings = load_moocs_derived_task_prototypes(["COT101"], FIXTURE_PATH)

        self.assertEqual([], warnings)
        self.assertEqual([], tasks)

    def test_missing_optional_file_is_not_a_warning(self) -> None:
        tasks, warnings = load_moocs_derived_task_prototypes(
            ["COT105"],
            Path("tests/fixtures/missing_moocs_task_candidates.json"),
        )

        self.assertEqual([], tasks)
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
