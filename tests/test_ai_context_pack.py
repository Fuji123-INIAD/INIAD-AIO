from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.ai_context_pack import (
    build_ai_ready_context_pack,
    format_ai_context_pack_for_mcp,
    summarize_ai_context_pack_for_mcp,
)
from scripts.evaluate_material_search import build_fixture_chunks


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import backend.main as backend_main
from backend.main import app


TASK_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "moocs_cot105_task_candidates_sanitized.json"
)


class AiContextPackCoreTests(unittest.TestCase):
    def test_build_pack_splits_tasks_and_materials_for_ai(self) -> None:
        task_payload = {
            "summary": "2 pending tasks",
            "caution": "task caution",
            "items": [
                {
                    "task_id": "course-rule:COT105",
                    "course_code": "COT105",
                    "course_title": "情報連携学概論 I",
                    "title": "COT105 課題",
                    "source": "course_rule",
                    "source_kind": "course_rule",
                    "kind": "rule_based_candidate",
                    "confidence": "medium",
                    "status": "todo",
                    "active": True,
                    "deadline_text": "unknown",
                    "deadline_confidence": "unknown",
                    "submission_text": "MOOCs",
                    "submission_confidence": "medium",
                    "evidence_summary": "rule evidence",
                    "evidence_url": "/api/tasks/course-rule:COT105/evidence",
                    "caution": "task caution",
                },
                {
                    "task_id": "moocs-task:COT105:abc",
                    "course_code": "COT105",
                    "course_title": "情報連携学概論 I",
                    "title": "第8回課題",
                    "source": "moocs",
                    "source_kind": "moocs",
                    "kind": "moocs_submission",
                    "confidence": "high",
                    "status": "todo",
                    "active": True,
                    "deadline_text": "MOOCs deadline text candidate: 2026-07-14 23:59",
                    "deadline_confidence": "low",
                    "submission_text": "MOOCs submit channel detected",
                    "submission_confidence": "medium",
                    "submission_format_text": "pptx or pdf",
                    "submission_format_confidence": "medium",
                    "primary_action_url": "https://moocs.example.test/task",
                    "evidence_summary": "MOOCs page (high)",
                    "evidence_url": "/api/tasks/moocs-task:COT105:abc/evidence",
                    "caution": "task caution",
                },
            ],
            "warnings": [],
        }
        material_payload = {
            "summary": "2 snippets",
            "query": "security",
            "mode": "hybrid",
            "caution": "material caution",
            "items": [
                {
                    "material_id": "text-material",
                    "chunk_id": "text-chunk",
                    "source_label": "text source",
                    "provider": "moocs_collect_search_index",
                    "source_type": "moocs_collect_search_index",
                    "extraction_method": "search_index",
                    "chunk_type": "slide",
                    "text_available": True,
                    "excerpt": "security " * 100,
                    "open_url": "https://example.test/text",
                },
                {
                    "material_id": "metadata-material",
                    "chunk_id": "metadata-chunk",
                    "source_label": "metadata source",
                    "provider": "moocs_collect_db_metadata",
                    "source_type": "pdf_metadata",
                    "extraction_method": "metadata_only",
                    "chunk_type": "metadata",
                    "text_available": False,
                    "excerpt": "metadata row",
                    "open_url": "https://example.test/metadata",
                },
            ],
            "warnings": [],
        }

        pack = build_ai_ready_context_pack(
            query="security",
            task_payload=task_payload,
            material_payload=material_payload,
            snippet_chars=120,
        )

        self.assertEqual("ai_ready_task_material_context", pack["pack_type"])
        self.assertIn("Use only", pack["instructions"])
        self.assertEqual(1, len(pack["tasks"]["rule_based"]))
        self.assertEqual(1, len(pack["tasks"]["moocs_derived"]))
        self.assertEqual("moocs", pack["tasks"]["moocs_derived"][0]["source"])
        self.assertEqual(1, len(pack["materials"]["text_snippets"]))
        self.assertEqual(1, len(pack["materials"]["metadata_only"]))
        self.assertEqual("medium", pack["materials"]["text_snippets"][0]["confidence"])
        self.assertEqual("low", pack["materials"]["metadata_only"][0]["confidence"])
        self.assertLessEqual(len(pack["materials"]["text_snippets"][0]["snippet"]), 120)
        self.assertTrue(pack["materials"]["metadata_only"][0]["metadata_only"])
        self.assertEqual(3, len(pack["cautions"]))

    def test_format_ai_context_pack_for_mcp_returns_sanitized_markdown(self) -> None:
        pack = {
            "status": "ok",
            "pack_type": "ai_ready_task_material_context",
            "query": "セキュリティ\x00",
            "summary": "AI-ready context for security.\x01",
            "tasks": {
                "count": 1,
                "rule_based": [
                    {
                        "title": "COT105 課題\x00",
                        "course_title": "情報連携学概論 I",
                        "confidence": "medium",
                        "caution": "公式締切はMOOCsで確認すること。\x02",
                    }
                ],
                "moocs_derived": [],
                "other": [],
                "caution": "task caution",
            },
            "materials": {
                "text_snippets": [
                    {
                        "title": "security.pdf",
                        "course_title": "情報連携学概論 I",
                        "lecture_title": "第08回 セキュリティ",
                        "provider": "moocs_collect",
                        "source_type": "moocs_collect_slide_text",
                        "extraction_method": "search_index",
                        "confidence": "medium",
                        "snippet": "暗号とセキュリティ\x00 " + ("長い本文 " * 80),
                    }
                ],
                "metadata_only": [
                    {
                        "title": "metadata-only row",
                        "provider": "moocs_collect_db_metadata",
                        "extraction_method": "metadata_only",
                        "text_available": False,
                        "warnings": [{"message": "本文は未取得\x03"}],
                    }
                ],
                "counts": {
                    "total": 2,
                    "text_snippets": 1,
                    "metadata_only": 1,
                },
                "caution": "material caution",
            },
            "cautions": ["AIO is a local context provider.", "material caution"],
            "warnings": [],
        }

        text = format_ai_context_pack_for_mcp(pack)
        summary = summarize_ai_context_pack_for_mcp(pack, text)

        self.assertIsInstance(text, str)
        for fragment in (
            "AI-ready context pack",
            "課題候補",
            "講義資料snippet",
            "metadata-only",
            "caution",
            "provider",
            "extraction_method",
        ):
            self.assertIn(fragment, text)
        self.assertLessEqual(len(text), 10000)
        for character in text:
            self.assertFalse(ord(character) < 32 and character not in "\n\r\t")
        self.assertEqual("compact_markdown", summary["format"])
        self.assertEqual(1, summary["counts"]["tasks"])
        self.assertEqual(1, summary["counts"]["text_snippets"])
        self.assertEqual(1, summary["counts"]["metadata_only"])


class AiContextPackApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        temp_path = Path(self.temp_dir.name)
        self.original_chunk_path = backend_main.MATERIAL_CHUNK_INDEX_PATH
        self.original_task_candidates_path = backend_main.MOOCS_TASK_CANDIDATES_PATH
        self.original_user_status_path = backend_main.USER_TASK_STATUS_PATH
        self.original_html_path = backend_main.HTML_EVIDENCE_PATH
        backend_main.MATERIAL_CHUNK_INDEX_PATH = temp_path / "material_chunk_index.json"
        backend_main.MOOCS_TASK_CANDIDATES_PATH = TASK_FIXTURE_PATH
        backend_main.USER_TASK_STATUS_PATH = temp_path / "user_task_status.json"
        backend_main.HTML_EVIDENCE_PATH = temp_path / "missing_html_evidence.json"
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False
        backend_main.MATERIAL_CHUNK_INDEX_PATH.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "chunks": [chunk.to_dict() for chunk in build_fixture_chunks()],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        backend_main.MATERIAL_CHUNK_INDEX_PATH = self.original_chunk_path
        backend_main.MOOCS_TASK_CANDIDATES_PATH = self.original_task_candidates_path
        backend_main.USER_TASK_STATUS_PATH = self.original_user_status_path
        backend_main.HTML_EVIDENCE_PATH = self.original_html_path
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False

    def test_ai_pack_endpoint_combines_cot105_tasks_and_materials(self) -> None:
        response = self.client.get(
            "/api/context/ai-pack",
            params={
                "q": "security",
                "course_code": "COT105",
                "course_title": "Info Link I",
                "lecture_key": "08",
                "mode": "hybrid",
                "material_limit": 5,
            },
        )

        self.assertEqual(200, response.status_code)
        pack = response.json()
        self.assertEqual("ok", pack["status"])
        self.assertEqual("ai_ready_task_material_context", pack["pack_type"])
        self.assertEqual(1, len(pack["tasks"]["rule_based"]))
        self.assertEqual(1, len(pack["tasks"]["moocs_derived"]))
        moocs_task = pack["tasks"]["moocs_derived"][0]
        self.assertEqual("moocs", moocs_task["source"])
        self.assertEqual("moocs_submission", moocs_task["kind"])
        self.assertEqual("low", moocs_task["deadline_confidence"])
        self.assertEqual("pptx or pdf", moocs_task["submission_format_text"])
        self.assertGreaterEqual(len(pack["materials"]["text_snippets"]), 1)
        self.assertGreaterEqual(len(pack["materials"]["metadata_only"]), 1)
        text_item = pack["materials"]["text_snippets"][0]
        self.assertEqual("moocs_collect_search_index", text_item["provider"])
        self.assertEqual("search_index", text_item["extraction_method"])
        self.assertEqual("medium", text_item["confidence"])
        metadata_item = pack["materials"]["metadata_only"][0]
        self.assertTrue(metadata_item["metadata_only"])
        self.assertEqual("low", metadata_item["confidence"])
        self.assertIn("AIO is a local context provider", pack["cautions"][0])


if __name__ == "__main__":
    unittest.main()
