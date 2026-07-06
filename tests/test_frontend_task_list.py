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
        self.assertIn("INIAD-AIO", html)
        self.assertIn("v1.0 Demo", html)
        self.assertIn(
            "この課題一覧は授業ルールに基づく課題候補です。",
            html,
        )
        self.assertIn(
            "course_code=COT101&course_code=SEM101&course_code=COT105",
            html,
        )
        self.assertIn('fetch("/api/tasks?" + ruleTaskQuery)', html)

    def test_legacy_ai_ui_is_hidden_and_pdf_search_is_visible(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('<section class="card question-card" hidden>', html)
        self.assertIn('<details class="card search-card" open>', html)
        self.assertIn('<section class="card answer-card" hidden>', html)
        self.assertIn('id="question"', html)
        self.assertIn('id="searchQuery"', html)
        self.assertIn('id="answer"', html)
        self.assertIn("/api/local/resources/search", html)
        self.assertIn("renderLocalPdfResults(data.results)", html)
        self.assertIn("PDFを開く", html)

    def test_index_renders_required_task_fields(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("task.short_name || task.course_code", html)
        self.assertIn("task.title ||", html)
        self.assertIn('appendTaskMeta(meta, "status"', html)
        self.assertIn('appendTaskMeta(meta, "active"', html)
        self.assertIn("task.estimated_deadline", html)
        self.assertIn("task.deadline", html)
        self.assertIn('table.className = "task-table"', html)
        self.assertIn('["科目", "区分", "やること", "期限", "開く", "状態", "根拠"]', html)
        self.assertIn("appendTaskTableRows(tableBody, task)", html)
        self.assertIn("task.short_name || task.course_code", html)
        self.assertIn("task.track", html)
        self.assertIn("task.description", html)
        self.assertIn("task.deadline_note", html)
        self.assertIn("createTaskPrimaryActionCell(task)", html)
        self.assertIn("task.primary_action_url", html)
        self.assertIn("task.primary_action_label", html)
        self.assertIn('link.target = "_blank"', html)
        self.assertIn('link.rel = "noopener noreferrer"', html)
        self.assertIn("task.submission_note", html)
        self.assertIn("task.caution_note", html)
        self.assertIn('["todo", "done", "ignored"]', html)
        self.assertIn("updateTaskStatus(task.id || task.task_id", html)
        self.assertIn('method: "PATCH"', html)
        self.assertIn("await loadTaskList()", html)
        self.assertIn("createTaskEvidenceButton(task)", html)
        self.assertIn("toggleTaskDetails(task, detailButton)", html)
        self.assertIn("evidence.label", html)
        self.assertIn("evidence.confidence", html)
        self.assertIn("item.dataset.evidenceType", html)
        self.assertIn("loadTaskEvidenceDetails(task.evidence_detail_url, container, button)", html)
        self.assertIn("renderTaskEvidenceDetails(container, data.evidence", html)
        self.assertIn("evidence.source", html)
        self.assertIn('detailRow.hidden = true', html)

    def test_task_list_styles_exist(self) -> None:
        css = (FRONTEND_DIR / "style.css").read_text(encoding="utf-8")

        self.assertIn(".task-card", css)
        self.assertIn(".task-table", css)
        self.assertIn(".task-row", css)
        self.assertIn(".task-description-cell", css)
        self.assertIn(".task-deadline-cell", css)
        self.assertIn(".task-primary-action-cell", css)
        self.assertIn(".task-primary-action-link", css)
        self.assertIn(".task-detail-row", css)
        self.assertIn(".task-supplemental-notes", css)
        self.assertIn(".task-error", css)
        self.assertIn(".task-warnings", css)
        self.assertIn(".task-status-select", css)
        self.assertIn(".task-evidence-detail-button", css)
        self.assertIn(".task-evidence-detail-list", css)
        self.assertIn(".local-resource-item", css)
        self.assertIn(".local-pdf-open-link", css)


if __name__ == "__main__":
    unittest.main()
