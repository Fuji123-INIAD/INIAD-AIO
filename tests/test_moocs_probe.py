from __future__ import annotations

import unittest

from backend.moocs_probe import (
    CoursePageProbeRecord,
    extract_accepting_status_from_text,
    extract_deadline_text_candidates_from_text,
    extract_keyword_contexts_from_text,
    page_to_dict,
)


class MoocsProbeEvidenceTests(unittest.TestCase):
    def test_text_evidence_extracts_small_contexts(self) -> None:
        text = (
            "第1回 Report の課題本文です。提出はMOOCsの提出ボタンから行ってください。 "
            "締切は2026年7月1日 23:59までです。現在、提出を受け付けています。 "
            "この文章の残りは通常の説明です。"
        )

        keyword_contexts = extract_keyword_contexts_from_text(text)
        deadline_candidates = extract_deadline_text_candidates_from_text(text)
        accepting_status = extract_accepting_status_from_text(text)

        self.assertTrue(any("Report" in context for context in keyword_contexts))
        self.assertTrue(any("提出" in context for context in keyword_contexts))
        self.assertTrue(any("締切" in context for context in deadline_candidates))
        self.assertIsNotNone(accepting_status)
        self.assertIn("受け付け", accepting_status or "")

    def test_page_to_dict_keeps_existing_shape_and_adds_optional_fields(self) -> None:
        record = CoursePageProbeRecord(
            page_title="Part 1 Quiz",
            page_url="https://moocs.iniad.org/courses/2026/COT105/08/02",
            materials=[],
            extracted_text="Quiz Submit by tomorrow.",
            keyword_contexts=["Quiz Submit by tomorrow."],
            buttons=[{"text": "提出", "type": "submit", "disabled": False}],
            submit_button_present=True,
            deadline_text_candidates=["Submit by tomorrow."],
            accepting_status_text=None,
            non_google_iframe_urls=["https://example.com/embed"],
            signin_redirect=False,
            content_fetched_at="2026-06-26T00:00:00+00:00",
            content_retrieval_method="dom:section.content",
        )

        payload = page_to_dict(record)

        self.assertEqual("Part 1 Quiz", payload["page_title"])
        self.assertEqual([], payload["materials"])
        self.assertEqual("Quiz Submit by tomorrow.", payload["extracted_text"])
        self.assertTrue(payload["submit_button_present"])
        self.assertEqual(False, payload["signin_redirect"])
        self.assertNotIn("input_values", payload)
        self.assertNotIn("html", payload)

    def test_empty_optional_fields_serialize_as_null_or_empty_lists(self) -> None:
        payload = page_to_dict(
            CoursePageProbeRecord(
                page_title="Reference",
                page_url="https://moocs.iniad.org/courses/2026/COT101/01-1/reference",
                materials=[],
            )
        )

        self.assertIsNone(payload["extracted_text"])
        self.assertEqual([], payload["keyword_contexts"])
        self.assertEqual([], payload["buttons"])
        self.assertIsNone(payload["submit_button_present"])
        self.assertEqual([], payload["deadline_text_candidates"])
        self.assertIsNone(payload["accepting_status_text"])


if __name__ == "__main__":
    unittest.main()
