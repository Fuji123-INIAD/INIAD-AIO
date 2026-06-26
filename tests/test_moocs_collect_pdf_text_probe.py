from __future__ import annotations

import unittest

from scripts.check_moocs_collect_page_join import page_url_to_key
from scripts.probe_moocs_collect_pdf_text import (
    extract_deadline_candidates,
    extract_keyword_contexts,
)


class MoocsCollectPdfTextProbeTests(unittest.TestCase):
    def test_extract_keyword_contexts_limits_snippet_length(self) -> None:
        text = (
            "前置き" * 80
            + "課題を提出してください。締切は次のページにあります。"
            + "補足" * 80
        )

        snippets = extract_keyword_contexts(
            text,
            max_snippets=2,
            snippet_chars=60,
        )

        self.assertEqual(2, len(snippets))
        self.assertEqual("課題", snippets[0]["keyword"])
        self.assertLessEqual(len(snippets[0]["snippet"]), 60)
        self.assertIn("課題", snippets[0]["snippet"])

    def test_extract_keyword_contexts_handles_english_case_insensitively(self) -> None:
        snippets = extract_keyword_contexts(
            "This ASSIGNMENT report is due before the next class.",
            max_snippets=3,
            snippet_chars=80,
        )

        keywords = {snippet["keyword"] for snippet in snippets}
        self.assertIn("report", keywords)
        self.assertIn("assignment", keywords)
        self.assertIn("due", keywords)

    def test_extract_deadline_candidates_finds_expected_short_forms(self) -> None:
        text = (
            "提出期限は4月21日火曜日23時59分です。"
            "別の小テストは6/10 23:59まで。"
            "レポートは2026-06-10 23:59に締切。"
            "演習は次の講義前日まで、確認は次回講義まで。"
        )

        candidates = extract_deadline_candidates(
            text,
            max_candidates=5,
            snippet_chars=40,
        )

        combined = " ".join(candidates)
        self.assertIn("4月21日火曜日23時59分", combined)
        self.assertIn("6/10 23:59", combined)
        self.assertIn("2026-06-10 23:59", combined)
        self.assertIn("次の講義前日まで", combined)
        self.assertIn("次回講義まで", combined)
        self.assertTrue(all(len(candidate) <= 40 for candidate in candidates))

    def test_page_url_to_key_reuse_normalizes_query_and_trailing_slash(self) -> None:
        self.assertEqual(
            "2026/COT105/00/exercise",
            page_url_to_key(
                "https://moocs.iniad.org/courses/2026/COT105/00/exercise/?debug=1"
            ),
        )


if __name__ == "__main__":
    unittest.main()
