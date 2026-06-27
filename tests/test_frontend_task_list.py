from __future__ import annotations

import unittest
from pathlib import Path


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class FrontendTaskListTests(unittest.TestCase):
    def test_index_fetches_rule_task_list_api(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="taskList"', html)
        self.assertIn('id="taskWarnings"', html)
        self.assertIn('id="taskError"', html)
        self.assertIn(
            "course_code=COT101&course_code=SEM101&course_code=COT105",
            html,
        )
        self.assertIn('fetch("/api/tasks?" + ruleTaskQuery)', html)

    def test_index_renders_required_task_fields(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("task.short_name || task.course_code", html)
        self.assertIn("task.title ||", html)
        self.assertIn('appendTaskMeta(meta, "status"', html)
        self.assertIn('appendTaskMeta(meta, "active"', html)
        self.assertIn("task.estimated_deadline", html)
        self.assertIn("task.deadline", html)
        self.assertIn('["todo", "done", "ignored"]', html)
        self.assertIn("updateTaskStatus(task.id || task.task_id", html)
        self.assertIn('method: "PATCH"', html)
        self.assertIn("await loadTaskList()", html)
        self.assertIn("renderTaskEvidence(task)", html)
        self.assertIn("evidence.label", html)
        self.assertIn("evidence.confidence", html)
        self.assertIn("item.dataset.evidenceType", html)
        self.assertIn("loadTaskEvidenceDetails(task.evidence_detail_url", html)
        self.assertIn("renderTaskEvidenceDetails(container, data.evidence", html)
        self.assertIn("evidence.source", html)
        self.assertIn("task-evidence-omitted", html)

    def test_task_list_styles_exist(self) -> None:
        css = (FRONTEND_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn(".task-card", css)
        self.assertIn(".task-item", css)
        self.assertIn(".task-error", css)
        self.assertIn(".task-warnings", css)
        self.assertIn(".task-controls", css)
        self.assertIn(".task-status-select", css)
        self.assertIn(".task-evidence", css)
        self.assertIn(".task-evidence-item", css)
        self.assertIn('[data-evidence-type="slides"]', css)
        self.assertIn(".task-evidence-detail-button", css)
        self.assertIn(".task-evidence-detail-list", css)
        self.assertIn(".task-evidence-omitted", css)


if __name__ == "__main__":
    unittest.main()
