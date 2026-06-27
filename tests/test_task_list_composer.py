from __future__ import annotations

import unittest

from backend.app.core.task_generator import (
    TaskPrototype,
    generate_course_rule_tasks,
)
from backend.app.core.task_list_composer import (
    TaskListItem,
    compose_task_list_items,
)
from backend.app.core.user_task_status import (
    UserTaskStatus,
    create_default_status,
    mark_done,
    mark_ignored,
)


class TaskListComposerTests(unittest.TestCase):
    def test_missing_status_is_treated_as_todo_and_active(self) -> None:
        task = self._task("task-1")

        items = compose_task_list_items([task])

        self.assertEqual(1, len(items))
        self.assertIsInstance(items[0], TaskListItem)
        self.assertEqual("todo", items[0].status)
        self.assertTrue(items[0].active)

    def test_done_status_is_inactive(self) -> None:
        task = self._task("task-1")
        status = mark_done(create_default_status("task-1"))

        items = compose_task_list_items([task], {"task-1": status})

        self.assertEqual("done", items[0].status)
        self.assertFalse(items[0].active)

    def test_ignored_status_is_inactive(self) -> None:
        task = self._task("task-1")
        status = mark_ignored(create_default_status("task-1"))

        items = compose_task_list_items([task], {"task-1": status})

        self.assertEqual("ignored", items[0].status)
        self.assertFalse(items[0].active)

    def test_unknown_status_is_ignored(self) -> None:
        task = self._task("task-1")
        unknown_status = UserTaskStatus(task_id="unknown-task", status="done")

        items = compose_task_list_items([task], {"unknown-task": unknown_status})

        self.assertEqual("todo", items[0].status)
        self.assertTrue(items[0].active)

    def test_input_order_is_preserved(self) -> None:
        tasks = [self._task("task-1"), self._task("task-2"), self._task("task-3")]

        items = compose_task_list_items(tasks)

        self.assertEqual(
            ["task-1", "task-2", "task-3"],
            [item.task_id for item in items],
        )

    def test_cot101_task_prototype_can_be_composed(self) -> None:
        tasks = generate_course_rule_tasks("COT101")

        items = compose_task_list_items(tasks)

        self.assertEqual(1, len(items))
        self.assertEqual("course-rule:COT101", items[0].task_id)
        self.assertEqual("COT101", items[0].course_code)
        self.assertEqual("COT101 課題", items[0].title)
        self.assertEqual("course_rule", items[0].source)
        self.assertEqual("todo", items[0].status)
        self.assertTrue(items[0].active)
        self.assertEqual("next_lecture_previous_day", items[0].deadline_rule)
        self.assertEqual("moocs", items[0].submission_channel)
        self.assertEqual("medium", items[0].confidence)

    @staticmethod
    def _task(task_id: str) -> TaskPrototype:
        return TaskPrototype(
            task_id=task_id,
            course_code="COT101",
            title=f"{task_id} title",
            source="course_rule",
            deadline_rule="next_lecture_previous_day",
            submission_channel="moocs",
            confidence="medium",
        )


if __name__ == "__main__":
    unittest.main()
