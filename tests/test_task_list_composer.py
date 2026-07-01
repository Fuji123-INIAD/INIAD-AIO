from __future__ import annotations

import unittest

from backend.app.core.task_generator import (
    TaskPrototype,
    generate_course_rule_tasks,
)
from backend.app.core.task_list_composer import (
    TaskEvidence,
    TaskListItem,
    compose_task_list_items,
    prepare_evidence,
    select_primary_action,
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
        self.assertIn("提出物", items[0].description)
        self.assertIn("次回授業", items[0].deadline_note)
        self.assertIn("MOOCs", items[0].submission_note)
        self.assertIn("Slides", items[0].caution_note)

    def test_display_fields_are_added_without_changing_course_code(self) -> None:
        item = compose_task_list_items([self._task("task-1")])[0]

        self.assertEqual("COT101", item.course_code)
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item.display_course_name)
        self.assertEqual("CS概論Ⅰ・基礎演習Ⅰ", item.short_name)
        self.assertEqual("COT", item.track)

    def test_unknown_course_display_fields_fall_back_to_course_code(self) -> None:
        item = compose_task_list_items([self._task("task-1", course_code="ABC999")])[0]

        self.assertEqual("ABC999", item.course_code)
        self.assertEqual("ABC999", item.display_course_name)
        self.assertEqual("ABC999", item.short_name)

    def test_course_rule_evidence_is_added(self) -> None:
        item = compose_task_list_items([self._task("task-1")])[0]

        self.assertEqual(1, len(item.evidence))
        self.assertIsInstance(item.evidence[0], TaskEvidence)
        self.assertEqual("course_rule", item.evidence[0].type)
        self.assertEqual("COT101 course rule", item.evidence[0].label)
        self.assertEqual("course_rule", item.evidence[0].source)
        self.assertEqual("medium", item.evidence[0].confidence)
        self.assertEqual(0, item.evidence_omitted_count)
        self.assertIsNone(item.primary_action_label)
        self.assertIsNone(item.primary_action_url)

    def test_extra_html_evidence_can_be_added(self) -> None:
        task = self._task("task-1")

        item = compose_task_list_items(
            [task],
            extra_evidence={
                "COT101": [
                    TaskEvidence(
                        type="html",
                        label="Assignment page",
                        source="https://example.test/assignment",
                        confidence="medium",
                    )
                ]
            },
        )[0]

        self.assertEqual(["course_rule", "html"], [evidence.type for evidence in item.evidence])
        self.assertEqual("Assignment page", item.evidence[1].label)
        self.assertEqual("Assignment page", item.primary_action_label)
        self.assertEqual("https://example.test/assignment", item.primary_action_url)

    def test_evidence_is_deduped_ranked_and_limited(self) -> None:
        evidence, omitted_count = prepare_evidence(
            [
                TaskEvidence("html", "HTML low", "same-html", "low"),
                TaskEvidence("slides", "Slides high", "slides-1", "high"),
                TaskEvidence("course_rule", "Rule", "course_rule", "medium"),
                TaskEvidence("html", "HTML high", "same-html", "high"),
                TaskEvidence("html", "HTML medium", "html-2", "medium"),
                TaskEvidence("html", "HTML low 3", "html-3", "low"),
                TaskEvidence("html", "HTML high 4", "html-4", "high"),
                TaskEvidence("html", "HTML high 5", "html-5", "high"),
            ]
        )

        self.assertEqual(5, len(evidence))
        self.assertEqual(3, omitted_count)
        self.assertEqual(["course_rule", "html", "html", "html", "html"], [item.type for item in evidence])
        self.assertEqual("Rule", evidence[0].label)
        self.assertEqual("HTML high", evidence[1].label)
        self.assertEqual("high", evidence[1].confidence)
        self.assertNotIn("Slides high", [item.label for item in evidence])

    def test_primary_action_prefers_html_then_confidence_and_url_sources(self) -> None:
        action = select_primary_action(
            [
                TaskEvidence("slides", "Slides high", "https://example.test/slides", "high"),
                TaskEvidence("html", "HTML low", "https://example.test/html-low", "low"),
                TaskEvidence("html", "HTML high page key", "2026/COT101/01/assignment", "high"),
                TaskEvidence("html", "HTML medium", "https://example.test/html-medium", "medium"),
            ]
        )

        self.assertIsNotNone(action)
        self.assertEqual("HTML medium", action.label)
        self.assertEqual("https://example.test/html-medium", action.source)

    @staticmethod
    def _task(task_id: str, course_code: str = "COT101") -> TaskPrototype:
        return TaskPrototype(
            task_id=task_id,
            course_code=course_code,
            title=f"{task_id} title",
            source="course_rule",
            deadline_rule="next_lecture_previous_day",
            submission_channel="moocs",
            confidence="medium",
            description="MOOCs の課題候補を確認してください。",
            deadline_note="実際の締切は MOOCs を確認してください。",
            submission_note="提出場所は MOOCs を確認してください。",
            caution_note="この一覧は候補です。",
        )


if __name__ == "__main__":
    unittest.main()
