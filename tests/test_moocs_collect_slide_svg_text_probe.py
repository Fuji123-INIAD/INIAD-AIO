from __future__ import annotations

import html
import unittest

from scripts.probe_moocs_collect_pdf_text import extract_deadline_candidates
from scripts.probe_moocs_collect_slide_svg_text import (
    decode_possible_escaped_svg_text,
    extract_aria_labels_from_embed_html,
    extract_svg_fragments,
)


class MoocsCollectSlideSvgTextProbeTests(unittest.TestCase):
    def test_extracts_aria_labels_from_escaped_svg(self) -> None:
        svg = (
            '<svg><g role="img" aria-label="課題は6/10 23:59までに提出">'
            "<path></path></g>"
            '<g role="img" aria-label="参考資料"></g></svg>'
        )
        escaped = html.escape(svg)
        embed_html = f"<html><script>var escaped = '{escaped}';</script></html>"

        labels = extract_aria_labels_from_embed_html(embed_html)

        self.assertEqual(
            ["課題は6/10 23:59までに提出", "参考資料"],
            labels,
        )

    def test_decodes_javascript_escaped_svg_markers(self) -> None:
        escaped = (
            r"\u003csvg\u003e"
            r"\u003cg role=\"img\" aria-label=\"assignment due\"\u003e"
            r"\u003c/g\u003e\u003c/svg\u003e"
        )

        decoded = decode_possible_escaped_svg_text(escaped)
        fragments = extract_svg_fragments(escaped)
        labels = extract_aria_labels_from_embed_html(escaped)

        self.assertIn("<svg>", decoded)
        self.assertEqual(1, len(fragments))
        self.assertEqual(["assignment due"], labels)

    def test_svg_aria_label_text_can_feed_deadline_extraction(self) -> None:
        labels = extract_aria_labels_from_embed_html(
            html.escape(
                '<svg><g role="img" aria-label="レポート提出期限 2026-06-10 23:59">'
                "</g></svg>"
            )
        )

        candidates = extract_deadline_candidates(" ".join(labels))

        self.assertTrue(any("2026-06-10 23:59" in item for item in candidates))


if __name__ == "__main__":
    unittest.main()
