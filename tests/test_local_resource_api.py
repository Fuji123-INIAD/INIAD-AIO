from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import backend.main as backend_main
from backend.main import app


class LocalResourceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.index_path = self.root / "data" / "local" / "resource_index.json"
        self.original_index_path = backend_main.LOCAL_RESOURCE_INDEX_PATH
        self.original_user_status_path = backend_main.USER_TASK_STATUS_PATH
        self.original_html_evidence_path = backend_main.HTML_EVIDENCE_PATH
        self.original_moocs_collect_db_path = backend_main.MOOCS_COLLECT_DB_PATH
        backend_main.LOCAL_RESOURCE_INDEX_PATH = self.index_path
        backend_main.USER_TASK_STATUS_PATH = (
            self.root / "data" / "local" / "user_task_status.json"
        )
        backend_main.HTML_EVIDENCE_PATH = self.root / "missing.json"
        backend_main.MOOCS_COLLECT_DB_PATH = None
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False
        self.client = TestClient(app)

    def tearDown(self) -> None:
        backend_main.LOCAL_RESOURCE_INDEX_PATH = self.original_index_path
        backend_main.USER_TASK_STATUS_PATH = self.original_user_status_path
        backend_main.HTML_EVIDENCE_PATH = self.original_html_evidence_path
        backend_main.MOOCS_COLLECT_DB_PATH = self.original_moocs_collect_db_path
        backend_main.USER_TASK_STATUSES.clear()
        backend_main.USER_TASK_STATUS_WARNINGS.clear()
        backend_main.USER_TASK_STATUS_LOADED = False

    def write_index(
        self,
        *,
        cache_text: str | None = None,
        card_text: str | None = None,
    ) -> dict[str, object]:
        pdf_path = self.root / "pdfs" / "security.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"%PDF-1.4\n% demo pdf\n")
        resource = {
            "resource_id": "local-resource:test-1",
            "course_code": None,
            "course_title": "情報連携学概論 I",
            "lecture_key": "08",
            "lecture_title": "セキュリティ",
            "title": "security.pdf",
            "resource_type": "pdf",
            "source_url": None,
            "local_path": str(pdf_path),
            "page_key": None,
            "text_available": cache_text is not None,
            "text_cache_path": "text_cache/test-1.json" if cache_text else None,
            "discovered_from": "filesystem",
            "card_text": card_text,
            "warnings": [],
        }
        self.index_path.parent.mkdir(parents=True)
        self.index_path.write_text(
            json.dumps({"resources": [resource], "warnings": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        if cache_text is not None:
            cache_path = self.index_path.parent / "text_cache" / "test-1.json"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "resource_id": resource["resource_id"],
                        "local_path": resource["local_path"],
                        "title": resource["title"],
                        "pages": [
                            {"page_number": 1, "text": "イントロ"},
                            {"page_number": 2, "text": cache_text},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return resource

    def test_list_local_resources_reads_index(self) -> None:
        self.write_index(cache_text="暗号とセキュリティの基本")

        response = self.client.get("/api/local/resources")

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("ok", data["status"])
        self.assertEqual(1, data["resource_count"])
        resource = data["resources"][0]
        self.assertEqual("security.pdf", resource["title"])
        self.assertEqual("情報連携学概論 I", resource["course_title"])
        self.assertEqual("08", resource["lecture_key"])
        self.assertTrue(resource["text_available"])
        self.assertEqual("unknown", resource["resource_kind"])
        self.assertEqual("resource", resource["entity_type"])
        self.assertEqual("filesystem", resource["source_kind"])
        self.assertIn("security.pdf", resource["card_text"])
        self.assertEqual(
            "/api/local/resources/local-resource%3Atest-1/file",
            resource["open_url"],
        )

    def test_search_local_resources_matches_text_cache(self) -> None:
        self.write_index(cache_text="暗号とセキュリティの基本を説明します。")

        response = self.client.get(
            "/api/local/resources/search",
            params={"q": "セキュリティ", "limit": 5},
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("ok", data["status"])
        self.assertEqual(1, data["result_count"])
        self.assertEqual("keyword", data["mode"])
        result = data["results"][0]
        self.assertEqual("local-resource:test-1", result["resource_id"])
        self.assertEqual(2, result["page_number"])
        self.assertIn("セキュリティ", result["snippet"])
        self.assertTrue(result["text_available"])

    def test_search_local_resources_matches_metadata_without_cache(self) -> None:
        self.write_index(cache_text=None)

        response = self.client.get(
            "/api/local/resources/search",
            params={"q": "情報連携学", "limit": 5},
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("ok", data["status"])
        self.assertEqual(1, data["result_count"])
        self.assertIsNone(data["results"][0]["page_number"])
        self.assertIn("情報連携学概論", data["results"][0]["snippet"])

    def test_search_local_resources_matches_context_card_text(self) -> None:
        self.write_index(cache_text=None, card_text="CardOnlyToken context card")

        response = self.client.get(
            "/api/local/resources/search",
            params={"q": "CardOnlyToken", "limit": 5},
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("ok", data["status"])
        self.assertEqual(1, data["result_count"])
        self.assertIn("CardOnlyToken", data["results"][0]["snippet"])
        self.assertEqual("CardOnlyToken context card", data["results"][0]["card_text"])

    def test_search_local_resources_supports_semantic_mode(self) -> None:
        self.write_index(cache_text=None, card_text="security privacy access control")

        response = self.client.get(
            "/api/local/resources/search",
            params={"q": "privacy", "mode": "semantic", "limit": 5},
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("ok", data["status"])
        self.assertEqual("semantic", data["mode"])
        self.assertEqual(1, data["result_count"])
        result = data["results"][0]
        self.assertEqual("semantic", result["search_mode"])
        self.assertGreater(result["search_score"], 0)

    def test_search_local_resources_rejects_unknown_mode(self) -> None:
        self.write_index(cache_text=None)

        response = self.client.get(
            "/api/local/resources/search",
            params={"q": "security", "mode": "surprise"},
        )

        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("error", data["status"])
        self.assertIn("mode", data["detail"])

    def test_get_local_resource_returns_cache_summary_without_full_text(self) -> None:
        long_text = "セキュリティ " + ("details " * 80)
        self.write_index(cache_text=long_text)

        response = self.client.get("/api/local/resources/local-resource:test-1")

        self.assertEqual(200, response.status_code)
        data = response.json()
        resource = data["resource"]
        self.assertEqual("security.pdf", resource["title"])
        self.assertTrue(resource["text_cache"]["available"])
        self.assertEqual(2, resource["text_cache"]["page_count"])
        preview = resource["text_cache"]["pages"][1]["text_preview"]
        self.assertLess(len(preview), len(long_text))

    def test_open_local_resource_file_serves_indexed_pdf(self) -> None:
        self.write_index(cache_text="セキュリティ")

        response = self.client.get("/api/local/resources/local-resource:test-1/file")

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response.headers["content-type"])
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))

    def test_missing_index_and_empty_query_do_not_crash(self) -> None:
        missing_response = self.client.get("/api/local/resources")
        empty_query_response = self.client.get("/api/local/resources/search?q=")

        self.assertEqual(200, missing_response.status_code)
        self.assertEqual("ok", missing_response.json()["status"])
        self.assertEqual([], missing_response.json()["resources"])
        self.assertTrue(missing_response.json()["warnings"])
        self.assertEqual(200, empty_query_response.status_code)
        self.assertEqual("error", empty_query_response.json()["status"])

    def test_missing_resource_id_returns_404(self) -> None:
        self.write_index(cache_text="セキュリティ")

        response = self.client.get("/api/local/resources/missing")

        self.assertEqual(404, response.status_code)

    def test_task_list_api_still_works(self) -> None:
        response = self.client.get(
            "/api/tasks",
            params=[
                ("course_code", "COT101"),
                ("course_code", "SEM101"),
                ("course_code", "COT105"),
            ],
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(3, response.json()["task_count"])


if __name__ == "__main__":
    unittest.main()
