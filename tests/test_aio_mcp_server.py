from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse

from backend.app.mcp.aio_server import AioMcpClient, MinimalMcpServer, call_aio_tool
from backend.app.core.task_backlog import TASK_BACKLOG_CAUTION
from scripts.smoke_aio_mcp import SmokeFailure, run_smoke


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse({"status": "ok", "echo": {"url": url, "params": params}})


class RoutedFakeSession:
    def __init__(self, *, empty_search: bool = False) -> None:
        self.empty_search = empty_search
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        path = urlparse(url).path
        if path == "/api/tasks":
            return FakeResponse(
                {
                    "course_codes": ["COT101", "SEM101", "COT105"],
                    "task_count": 3,
                    "active_count": 3,
                    "items": [{"task_id": "course-rule:COT101"}],
                    "warnings": [],
                }
            )
        if path == "/api/tasks/pending":
            return FakeResponse(
                {
                    "status": "ok",
                    "summary": "現在AIO上で確認が必要な課題候補は1件です。",
                    "count": 1,
                    "items": [
                        {
                            "task_id": "course-rule:COT105",
                            "course_code": "COT105",
                            "title": "COT105 課題",
                            "status": "todo",
                        }
                    ],
                    "caution": TASK_BACKLOG_CAUTION,
                }
            )
        if path == "/api/tasks/backlog/summary":
            return FakeResponse(
                {
                    "status": "ok",
                    "summary": "現在AIO上で確認が必要な課題候補は1件です。",
                    "count": 1,
                    "items": [],
                    "caution": TASK_BACKLOG_CAUTION,
                }
            )
        if path == "/api/local/resources":
            return FakeResponse(
                {
                    "status": "ok",
                    "resource_count": 1,
                    "resources": [
                        {
                            "resource_id": "local-resource:test-1",
                            "title": "security.pdf",
                            "open_url": "/api/local/resources/local-resource%3Atest-1/file",
                        }
                    ],
                    "warnings": [],
                }
            )
        if path == "/api/local/resources/search":
            results = [] if self.empty_search else [
                {
                    "resource_id": "local-resource:test-1",
                    "title": "security.pdf",
                    "snippet": "セキュリティ",
                }
            ]
            return FakeResponse(
                {
                    "status": "ok",
                    "query": params["q"],
                    "mode": params["mode"],
                    "result_count": len(results),
                    "results": results,
                    "warnings": [],
                }
            )
        if path == "/api/local/resources/local-resource%3Atest-1":
            return FakeResponse(
                {
                    "status": "ok",
                    "resource": {
                        "resource_id": "local-resource:test-1",
                        "title": "security.pdf",
                        "text_cache": {"available": False},
                    },
                    "warnings": [],
                }
            )
        if path == "/api/context/search":
            return FakeResponse(
                {
                    "status": "ok",
                    "summary": "セキュリティ の関連資料snippetは1件です。",
                    "query": params["q"],
                    "mode": params["mode"],
                    "items": [
                        {
                            "material_id": "material:test-1",
                            "chunk_id": "chunk:test-1",
                            "source_label": "情報連携学概論 I / 第08回 セキュリティ / security.pdf",
                            "source_type": "moocs_collect_slide_text",
                            "provider": "moocs_collect",
                            "extraction_method": "search_index",
                            "chunk_type": "slide",
                            "text_available": True,
                            "excerpt": "暗号とセキュリティ",
                            "open_url": "/api/local/resources/local-resource%3Atest-1/file",
                        }
                    ],
                    "caution": "検索対象にはMOOCs-Collect由来テキストが含まれます。",
                }
            )
        if path == "/api/context/ai-pack":
            return FakeResponse(
                {
                    "status": "ok",
                    "pack_type": "ai_ready_task_material_context",
                    "query": params["q"],
                    "summary": "AI-ready context for security.",
                    "instructions": "Use only facts present in this tool result.",
                    "tasks": {
                        "summary": "1 pending task",
                        "count": 1,
                        "rule_based": [
                            {
                                "task_id": "course-rule:COT105",
                                "course_code": "COT105",
                                "course_title": "情報連携学概論 I",
                                "title": "COT105 課題",
                                "source": "course_rule",
                                "source_kind": "course_rule",
                                "kind": "rule_based_candidate",
                                "confidence": "medium",
                                "deadline_text": "unknown",
                                "deadline_confidence": "unknown",
                                "submission_text": "MOOCs",
                                "submission_confidence": "medium",
                                "open_url": None,
                                "evidence_summary": "COT105 course rule (medium)",
                                "evidence_url": "/api/tasks/course-rule:COT105/evidence",
                                "caution": TASK_BACKLOG_CAUTION,
                            }
                        ],
                        "moocs_derived": [],
                        "other": [],
                        "caution": TASK_BACKLOG_CAUTION,
                    },
                    "materials": {
                        "summary": "1 material snippet",
                        "query": params["q"],
                        "mode": params["mode"],
                        "text_snippets": [
                            {
                                "material_id": "material:test-1",
                                "chunk_id": "chunk:test-1",
                                "source_label": "情報連携学概論 I / 第08回 セキュリティ / security.pdf",
                                "course_title": "情報連携学概論 I",
                                "lecture_title": "第08回 セキュリティ",
                                "title": "security.pdf",
                                "source_kind": "moocs_collect",
                                "provider": "moocs_collect",
                                "source_type": "moocs_collect_slide_text",
                                "extraction_method": "search_index",
                                "chunk_type": "slide",
                                "metadata_only": False,
                                "text_available": True,
                                "confidence": "medium",
                                "open_url": "/api/local/resources/local-resource%3Atest-1/file",
                                "snippet": "暗号とセキュリティ",
                            }
                        ],
                        "metadata_only": [
                            {
                                "material_id": "material:metadata-1",
                                "chunk_id": "chunk:metadata-1",
                                "source_label": "情報連携学概論 I / 第08回 セキュリティ / metadata",
                                "title": "metadata row",
                                "source_kind": "moocs_collect",
                                "provider": "moocs_collect_db_metadata",
                                "source_type": "pdf_metadata",
                                "extraction_method": "metadata_only",
                                "chunk_type": "metadata",
                                "metadata_only": True,
                                "text_available": False,
                                "confidence": "low",
                                "warnings": [{"message": "本文は未取得です。"}],
                            }
                        ],
                        "counts": {
                            "total": 2,
                            "text_snippets": 1,
                            "metadata_only": 1,
                        },
                        "caution": "検索対象にはMOOCs-Collect由来テキストが含まれます。",
                    },
                    "cautions": [
                        "AIO is a local context provider.",
                        TASK_BACKLOG_CAUTION,
                        "検索対象にはMOOCs-Collect由来テキストが含まれます。",
                    ],
                    "warnings": [],
                }
            )
        if path == "/api/materials/material%3Atest-1":
            return FakeResponse(
                {
                    "status": "ok",
                    "material": {
                        "material_id": "material:test-1",
                        "local_resource_id": "local-resource:test-1",
                        "title": "security.pdf",
                        "text_available": True,
                    },
                    "chunks": [
                        {
                            "material_id": "material:test-1",
                            "chunk_id": "chunk:test-1",
                            "source_label": "情報連携学概論 I / 第08回 セキュリティ / security.pdf",
                            "source_type": "moocs_collect_slide_text",
                            "provider": "moocs_collect",
                            "extraction_method": "search_index",
                            "chunk_type": "slide",
                            "text_available": True,
                            "text": "暗号とセキュリティ",
                        }
                    ],
                    "caution": "検索対象にはMOOCs-Collect由来テキストが含まれます。",
                }
            )
        if path == "/api/materials/local-resource%3Atest-1":
            return FakeResponse(
                {
                    "status": "ok",
                    "material": {
                        "material_id": "material:test-1",
                        "local_resource_id": "local-resource:test-1",
                        "title": "security.pdf",
                        "text_available": False,
                    },
                    "chunks": [],
                    "caution": "検索対象にはMOOCs-Collect由来テキストが含まれます。",
                }
            )
        return FakeResponse({"status": "error", "detail": f"unexpected path: {path}"})


class AioMcpServerTests(unittest.TestCase):
    def test_list_tasks_uses_default_demo_courses(self) -> None:
        session = FakeSession()
        client = AioMcpClient(base_url="http://aio.test", session=session)

        result = client.list_tasks()

        self.assertEqual("ok", result["status"])
        call = session.calls[0]
        self.assertEqual("http://aio.test/api/tasks", call["url"])
        self.assertEqual(
            [
                ("course_code", "COT101"),
                ("course_code", "SEM101"),
                ("course_code", "COT105"),
            ],
            call["params"],
        )

    def test_search_local_resources_tool_passes_query_limit_and_mode(self) -> None:
        session = FakeSession()
        client = AioMcpClient(base_url="http://aio.test", session=session)

        call_aio_tool(
            client,
            "search_local_resources",
            {"query": "security", "limit": 3, "mode": "hybrid"},
        )

        call = session.calls[0]
        self.assertEqual("http://aio.test/api/local/resources/search", call["url"])
        self.assertEqual(
            {"q": "security", "limit": 3, "mode": "hybrid"},
            call["params"],
        )

    def test_get_resource_and_task_ids_are_path_encoded(self) -> None:
        session = FakeSession()
        client = AioMcpClient(base_url="http://aio.test", session=session)

        client.get_task_evidence("course-rule:COT101")
        client.get_local_resource("local-resource:test-1")

        task_path = urlparse(session.calls[0]["url"]).path
        resource_path = urlparse(session.calls[1]["url"]).path
        self.assertEqual("/api/tasks/course-rule%3ACOT101/evidence", task_path)
        self.assertEqual("/api/local/resources/local-resource%3Atest-1", resource_path)

    def test_json_rpc_tool_call_returns_structured_content(self) -> None:
        session = FakeSession()
        server = MinimalMcpServer(
            AioMcpClient(base_url="http://aio.test", session=session)
        )

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_tasks",
                    "arguments": {"course_codes": ["COT101"]},
                },
            }
        )

        self.assertIsNotNone(response)
        result = response["result"]
        self.assertEqual("ok", result["structuredContent"]["status"])
        self.assertEqual([("course_code", "COT101")], session.calls[0]["params"])

    def test_json_rpc_tool_text_is_ascii_safe_for_japanese(self) -> None:
        session = RoutedFakeSession()
        server = MinimalMcpServer(
            AioMcpClient(base_url="http://aio.test", session=session)
        )

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "summarize_task_backlog", "arguments": {}},
            }
        )

        text = response["result"]["content"][0]["text"]
        self.assertNotIn("現在AIO", text)
        self.assertIn("\\u73fe\\u5728", text)
        self.assertEqual("ok", json.loads(text)["status"])

    def test_material_context_tools_call_expected_endpoints(self) -> None:
        session = RoutedFakeSession()
        client = AioMcpClient(base_url="http://aio.test", session=session)

        search = call_aio_tool(
            client,
            "search_material_context",
            {"query": "セキュリティ", "mode": "hybrid", "limit": 3},
        )
        detail = call_aio_tool(
            client,
            "get_material_context",
            {"material_id": "material:test-1"},
        )

        self.assertEqual("ok", search["status"])
        self.assertEqual(1, len(search["items"]))
        self.assertEqual("security.pdf", detail["material"]["title"])

    def test_prepare_course_context_tool_calls_ai_pack_endpoint(self) -> None:
        session = RoutedFakeSession()
        client = AioMcpClient(base_url="http://aio.test", session=session)

        pack = call_aio_tool(
            client,
            "prepare_course_context",
            {
                "query": "セキュリティ",
                "course_title": "情報連携学概論 I",
                "lecture_key": "08",
                "mode": "hybrid",
                "material_limit": 3,
            },
        )

        self.assertEqual("ok", pack["status"])
        self.assertEqual("ai_ready_task_material_context", pack["pack_type"])
        self.assertEqual(1, len(pack["tasks"]["rule_based"]))
        self.assertEqual(1, len(pack["materials"]["text_snippets"]))
        self.assertEqual(1, len(pack["materials"]["metadata_only"]))
        call = session.calls[0]
        self.assertEqual("http://aio.test/api/context/ai-pack", call["url"])
        self.assertEqual("セキュリティ", call["params"]["q"])
        self.assertEqual("情報連携学概論 I", call["params"]["course_title"])

    def test_json_rpc_prepare_course_context_returns_compact_text(self) -> None:
        session = RoutedFakeSession()
        server = MinimalMcpServer(
            AioMcpClient(base_url="http://aio.test", session=session)
        )

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "prepare_course_context",
                    "arguments": {"query": "セキュリティ", "mode": "hybrid"},
                },
            }
        )

        self.assertIsNotNone(response)
        result = response["result"]
        content = result["content"]
        self.assertIsInstance(content, list)
        text = content[0]["text"]
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
        structured = result["structuredContent"]
        self.assertEqual("compact_markdown", structured["format"])
        self.assertEqual(1, structured["counts"]["tasks"])
        self.assertEqual(1, structured["counts"]["text_snippets"])
        self.assertEqual(1, structured["counts"]["metadata_only"])
        self.assertNotIn("tasks", structured)


class AioMcpSmokeTests(unittest.TestCase):
    def test_smoke_runs_initialize_tools_and_demo_tool_calls(self) -> None:
        session = RoutedFakeSession()

        report = run_smoke(
            base_url="http://aio.test",
            session=session,
            query="セキュリティ",
        )

        self.assertEqual("ok", report["status"])
        self.assertIn("list_tasks", report["tools"])
        self.assertIn("list_pending_tasks", report["tools"])
        self.assertIn("search_local_resources", report["tools"])
        self.assertIn("search_material_context", report["tools"])
        self.assertIn("prepare_course_context", report["tools"])
        self.assertEqual(3, report["task_count"])
        self.assertEqual(1, report["pending_task_count"])
        self.assertEqual(1, report["task_backlog_count"])
        self.assertEqual(1, report["resource_count"])
        self.assertEqual(1, report["search_result_count"])
        self.assertEqual(1, report["material_context_count"])
        self.assertEqual(1, report["material_text_snippet_count"])
        self.assertEqual(0, report["material_metadata_only_count"])
        self.assertEqual(1, report["ai_context_task_count"])
        self.assertEqual(2, report["ai_context_material_count"])
        self.assertEqual(1, report["ai_context_text_snippet_count"])
        self.assertEqual(1, report["ai_context_metadata_only_count"])
        self.assertEqual(1, report["lecture_material_count"])
        self.assertEqual("material:test-1", report["material_detail_id"])
        self.assertTrue(report["material_detail_checked"])
        self.assertEqual("local-resource:test-1", report["detail_resource_id"])
        self.assertTrue(report["detail_checked"])
        self.assertTrue(report["resource_summary_checked"])

    def test_smoke_fails_when_required_search_is_empty(self) -> None:
        session = RoutedFakeSession(empty_search=True)

        with self.assertRaises(SmokeFailure):
            run_smoke(
                base_url="http://aio.test",
                session=session,
                query="セキュリティ",
            )


if __name__ == "__main__":
    unittest.main()
