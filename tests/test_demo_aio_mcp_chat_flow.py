from __future__ import annotations

import unittest

from scripts.demo_aio_mcp_chat_flow import (
    clean_snippet,
    first_material_context_item,
    render_markdown,
)


class DemoAioMcpChatFlowDisplayTests(unittest.TestCase):
    def test_first_material_context_item_prefers_text_over_metadata(self) -> None:
        context = {
            "items": [
                {
                    "material_id": "metadata-material",
                    "chunk_type": "metadata",
                    "text_available": False,
                },
                {
                    "material_id": "text-material",
                    "chunk_type": "slide",
                    "text_available": True,
                },
            ]
        }

        item = first_material_context_item(context)

        self.assertIsNotNone(item)
        self.assertEqual("text-material", item["material_id"])

    def test_render_splits_text_and_metadata_and_shortens_snippets(self) -> None:
        long_snippet = "security " * 80
        backlog = {
            "summary": "2 pending tasks",
            "items": [],
            "caution": "Task list is a candidate backlog.",
        }
        context = {
            "summary": "2 material candidates",
            "caution": "Material snippets are candidate context.",
            "items": [
                {
                    "material_id": "metadata-material",
                    "source_label": "Metadata PDF",
                    "chunk_type": "metadata",
                    "text_available": False,
                    "provider": "moocs_collect_db_metadata",
                    "source_type": "pdf_metadata",
                    "extraction_method": "metadata_only",
                    "excerpt": "metadata only row",
                    "open_url": "http://127.0.0.1:8000/files/metadata.pdf",
                    "score": 1.0,
                },
                {
                    "material_id": "text-material",
                    "source_label": "Search Index Slide",
                    "chunk_type": "slide",
                    "text_available": True,
                    "provider": "moocs_collect_search_index",
                    "source_type": "moocs_collect_search_index",
                    "extraction_method": "search_index",
                    "excerpt": long_snippet,
                    "score": 8.0,
                },
            ],
        }
        material = {
            "chunks": [
                {
                    "source_label": "Metadata chunk",
                    "chunk_type": "metadata",
                    "text_available": False,
                    "provider": "moocs_collect_db_metadata",
                    "source_type": "pdf_metadata",
                    "extraction_method": "metadata_only",
                    "text": "metadata chunk text",
                },
                {
                    "source_label": "Text chunk",
                    "chunk_type": "slide",
                    "text_available": True,
                    "provider": "moocs_collect_search_index",
                    "source_type": "moocs_collect_search_index",
                    "extraction_method": "search_index",
                    "text": long_snippet,
                },
            ]
        }

        output = render_markdown(backlog, context, material, query="security")

        self.assertIn("Text snippets", output)
        self.assertIn("Metadata-only fallback", output)
        self.assertLess(output.index("Text snippets"), output.index("Metadata-only fallback"))
        self.assertIn("provider=moocs_collect_search_index", output)
        self.assertIn("source_type=moocs_collect_search_index", output)
        self.assertIn("metadata-only: 本文未抽出", output)
        self.assertIn("...", output)
        first_material_section = output.split("## 3. First material snippets", 1)[1]
        self.assertIn("Text chunk", first_material_section)
        self.assertNotIn("metadata chunk text", first_material_section)

    def test_clean_snippet_removes_control_characters(self) -> None:
        self.assertEqual("hello world", clean_snippet("hello\x00\nworld", 80))


if __name__ == "__main__":
    unittest.main()
