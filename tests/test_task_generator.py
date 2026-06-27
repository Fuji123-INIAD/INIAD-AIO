from __future__ import annotations

import unittest

from backend.app.core.task_generator import (
    TaskPrototype,
    generate_course_rule_tasks,
)


class TaskGeneratorTests(unittest.TestCase):
    def test_cot101_task_is_generated(self) -> None:
        tasks = generate_course_rule_tasks("COT101")

        self.assertEqual(1, len(tasks))
        self.assertIsInstance(tasks[0], TaskPrototype)
        self.assertEqual("course-rule:COT101", tasks[0].task_id)
        self.assertEqual("COT101", tasks[0].course_code)
        self.assertEqual("COT101 課題", tasks[0].title)
        self.assertEqual("next_lecture_previous_day", tasks[0].deadline_rule)
        self.assertEqual("moocs", tasks[0].submission_channel)
        self.assertEqual("medium", tasks[0].confidence)

    def test_sem101_task_is_generated(self) -> None:
        tasks = generate_course_rule_tasks("SEM101")

        self.assertEqual(1, len(tasks))
        self.assertEqual("course-rule:SEM101", tasks[0].task_id)
        self.assertEqual("SEM101", tasks[0].course_code)
        self.assertEqual("SEM101 課題", tasks[0].title)
        self.assertEqual("same_week_sunday_2359", tasks[0].deadline_rule)
        self.assertEqual("email_to_instructor", tasks[0].submission_channel)
        self.assertEqual("medium", tasks[0].confidence)

    def test_cot105_task_is_generated(self) -> None:
        tasks = generate_course_rule_tasks("COT105")

        self.assertEqual(1, len(tasks))
        self.assertEqual("course-rule:COT105", tasks[0].task_id)
        self.assertEqual("COT105", tasks[0].course_code)
        self.assertEqual("COT105 課題", tasks[0].title)
        self.assertEqual("explicit_or_unknown", tasks[0].deadline_rule)
        self.assertEqual("moocs", tasks[0].submission_channel)
        self.assertEqual("low", tasks[0].confidence)

    def test_unknown_course_returns_empty_list(self) -> None:
        self.assertEqual([], generate_course_rule_tasks("UNKNOWN101"))

    def test_generated_task_source_is_course_rule(self) -> None:
        tasks = generate_course_rule_tasks(" cot101 ")

        self.assertEqual(1, len(tasks))
        self.assertEqual("course_rule", tasks[0].source)

    def test_generated_task_does_not_hold_deadline_values(self) -> None:
        task = generate_course_rule_tasks("COT101")[0]

        self.assertFalse(hasattr(task, "deadline_at"))
        self.assertFalse(hasattr(task, "estimated_deadline_at"))


if __name__ == "__main__":
    unittest.main()
