from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.core.material_chunks import chunk_material_texts
from backend.app.core.material_search import search_context_pack, search_material_chunks
from backend.app.core.material_text import material_texts_from_local_resources
from backend.app.core.task_backlog import (
    TASK_BACKLOG_CAUTION,
    build_pending_tasks_payload,
)


class TaskBacklogTests(unittest.TestCase):
    def test_pending_tasks_excludes_done_and_ignored_with_caution(self) -> None:
        payload = {
            "items": [
                {"task_id": "todo", "status": "todo", "active": True, "title": "見る"},
                {"task_id": "done", "status": "done", "active": False, "title": "済み"},
                {"task_id": "hidden", "status": "hidden", "active": False, "title": "非表示"},
            ],
            "warnings": [],
        }

        result = build_pending_tasks_payload(payload)

        self.assertEqual("ok", result["status"])
        self.assertEqual(1, result["count"])
        self.assertEqual("todo", result["items"][0]["task_id"])
        self.assertEqual(TASK_BACKLOG_CAUTION, result["caution"])
        self.assertEqual("unknown", result["items"][0]["deadline_text"])


class MaterialPipelineTests(unittest.TestCase):
    def test_local_resource_metadata_fallback_chunks_and_searches(self) -> None:
        resource = {
            "resource_id": "local-resource:test-1",
            "course_code": "COT105",
            "course_title": "情報連携学概論 I",
            "lecture_key": "08",
            "lecture_title": "セキュリティ",
            "title": "Part1.pdf",
            "local_path": "C:/demo/Part1.pdf",
            "text_available": False,
            "text_cache_path": None,
            "card_text": "セキュリティの資料。PDF本文テキストは未抽出。",
            "warnings": [],
        }

        materials = material_texts_from_local_resources([resource], include_text_cache=True)
        chunks = chunk_material_texts(materials)
        results = search_material_chunks(
            chunks,
            query="セキュリティ",
            mode="keyword",
            filters={"course_code": "COT105", "lecture_key": "08"},
        )

        self.assertEqual(1, len(materials))
        self.assertFalse(materials[0].text_available)
        self.assertEqual("pdf_metadata", materials[0].source_type)
        self.assertEqual("metadata", chunks[0].chunk_type)
        self.assertEqual(1, len(results))
        self.assertIn("セキュリティ", results[0]["excerpt"])

    def test_text_cache_material_prefers_text_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "resource_index.json"
            cache_path = root / "text_cache" / "test.json"
            cache_path.parent.mkdir()
            cache_path.write_text(
                json.dumps(
                    {"pages": [{"page_number": 1, "text": "暗号とセキュリティの基本"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resource = {
                "resource_id": "local-resource:test-1",
                "course_code": "COT105",
                "course_title": "情報連携学概論 I",
                "lecture_key": "08",
                "lecture_title": "セキュリティ",
                "title": "Part1.pdf",
                "local_path": "C:/demo/Part1.pdf",
                "text_available": True,
                "text_cache_path": "text_cache/test.json",
                "card_text": "metadata only",
                "warnings": [],
            }

            materials = material_texts_from_local_resources(
                [resource],
                index_path=index_path,
                include_text_cache=True,
            )
            chunks = chunk_material_texts(materials)
            pack = search_context_pack(
                chunks,
                query="暗号",
                mode="hybrid",
                limit=5,
                filters={},
            )

        self.assertTrue(materials[0].text_available)
        self.assertEqual("pdf_native", materials[0].source_type)
        self.assertEqual("pdf_page", chunks[0].chunk_type)
        self.assertEqual("ok", pack["status"])
        self.assertIn("暗号", pack["items"][0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
