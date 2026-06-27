from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.app.core.user_task_status import (
    UserTaskStatus,
    create_default_status,
    is_active,
    mark_done,
    mark_ignored,
    mark_todo,
)


class UserTaskStatusTests(unittest.TestCase):
    def test_default_status_is_todo(self) -> None:
        now = datetime(2026, 6, 27, 1, 0, tzinfo=timezone.utc)

        status = create_default_status("course-rule:COT101", now=now)

        self.assertEqual("course-rule:COT101", status.task_id)
        self.assertEqual("todo", status.status)
        self.assertEqual(now, status.updated_at)
        self.assertIsNone(status.checked_at)

    def test_mark_done_sets_done(self) -> None:
        created_at = datetime(2026, 6, 27, 1, 0, tzinfo=timezone.utc)
        done_at = datetime(2026, 6, 27, 2, 0, tzinfo=timezone.utc)
        status = create_default_status("course-rule:COT101", now=created_at)

        done = mark_done(status, now=done_at)

        self.assertEqual("done", done.status)
        self.assertEqual(done_at, done.updated_at)
        self.assertEqual(done_at, done.checked_at)

    def test_mark_todo_sets_todo_and_clears_checked_at(self) -> None:
        done_at = datetime(2026, 6, 27, 2, 0, tzinfo=timezone.utc)
        todo_at = datetime(2026, 6, 27, 3, 0, tzinfo=timezone.utc)
        done = mark_done(create_default_status("course-rule:COT101"), now=done_at)

        todo = mark_todo(done, now=todo_at)

        self.assertEqual("todo", todo.status)
        self.assertEqual(todo_at, todo.updated_at)
        self.assertIsNone(todo.checked_at)

    def test_mark_ignored_sets_ignored_and_clears_checked_at(self) -> None:
        done_at = datetime(2026, 6, 27, 2, 0, tzinfo=timezone.utc)
        ignored_at = datetime(2026, 6, 27, 3, 0, tzinfo=timezone.utc)
        done = mark_done(create_default_status("course-rule:COT101"), now=done_at)

        ignored = mark_ignored(done, now=ignored_at)

        self.assertEqual("ignored", ignored.status)
        self.assertEqual(ignored_at, ignored.updated_at)
        self.assertIsNone(ignored.checked_at)

    def test_is_active_is_true_only_for_todo(self) -> None:
        todo = UserTaskStatus(task_id="task-1", status="todo")
        done = UserTaskStatus(task_id="task-1", status="done", checked_at=datetime.now(timezone.utc))
        ignored = UserTaskStatus(task_id="task-1", status="ignored")

        self.assertTrue(is_active(todo))
        self.assertFalse(is_active(done))
        self.assertFalse(is_active(ignored))

    def test_checked_at_is_allowed_only_for_done(self) -> None:
        checked_at = datetime(2026, 6, 27, 2, 0, tzinfo=timezone.utc)

        UserTaskStatus(task_id="task-1", status="done", checked_at=checked_at)
        with self.assertRaises(ValueError):
            UserTaskStatus(task_id="task-1", status="todo", checked_at=checked_at)
        with self.assertRaises(ValueError):
            UserTaskStatus(task_id="task-1", status="ignored", checked_at=checked_at)

    def test_invalid_status_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            UserTaskStatus(task_id="task-1", status="open")


if __name__ == "__main__":
    unittest.main()
