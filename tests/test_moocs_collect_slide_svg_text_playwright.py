from __future__ import annotations

import unittest

from scripts.probe_moocs_collect_slide_svg_text_playwright import (
    build_slide_result,
    dedupe_texts,
    is_signin_redirect,
)


class MoocsCollectSlideSvgTextPlaywrightTests(unittest.TestCase):
    def test_signin_redirect_detection(self) -> None:
        self.assertTrue(is_signin_redirect("https://accounts.google.com/signin/v2"))
        self.assertTrue(is_signin_redirect("https://docs.google.com/", "ChooseAccount"))
        self.assertFalse(is_signin_redirect("https://docs.google.com/presentation/d/example"))

    def test_dedupe_texts_normalizes_whitespace(self) -> None:
        self.assertEqual(
            ["課題 提出", "assignment due"],
            dedupe_texts([" 課題\n提出 ", "課題 提出", "", "assignment due"]),
        )

    def test_build_slide_result_reports_case4_shape_and_snippet_limits(self) -> None:
        row = {
            "slide_url": "https://docs.google.com/presentation/d/example/pubembed",
            "page_key": "2026/COT000/00/exercise",
            "slide_index": 1,
        }

        result = build_slide_result(
            row=row,
            page_loaded=True,
            final_url="https://docs.google.com/presentation/d/example/pubembed",
            title="Dummy Slides",
            svg_count=2,
            aria_labels=[
                "課題を提出してください。期限は6/10 23:59です。",
                "This assignment report is due next week.",
            ],
            max_snippets=2,
            snippets_per_slide=2,
            snippet_chars=40,
        )

        self.assertTrue(result["page_loaded"])
        self.assertTrue(result["svg_found"])
        self.assertEqual(2, result["aria_label_count"])
        self.assertEqual(2, result["snippet_count"])
        self.assertFalse(result["signin_redirect"])
        self.assertTrue(all(
            len(item["snippet"]) <= 40
            for item in result["keyword_context_snippets"]
        ))

    def test_build_slide_result_reports_case3_shape(self) -> None:
        row = {
            "slide_url": "https://docs.google.com/presentation/d/example/pubembed",
            "page_key": "2026/COT000/00/exercise",
            "slide_index": 1,
        }

        result = build_slide_result(
            row=row,
            page_loaded=True,
            final_url="https://docs.google.com/presentation/d/example/pubembed",
            title="Dummy Slides",
            svg_count=1,
            aria_labels=[],
            max_snippets=5,
            snippets_per_slide=3,
            snippet_chars=80,
        )

        self.assertTrue(result["page_loaded"])
        self.assertTrue(result["svg_found"])
        self.assertEqual(0, result["aria_label_count"])
        self.assertEqual(0, result["snippet_count"])


if __name__ == "__main__":
    unittest.main()
