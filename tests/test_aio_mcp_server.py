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
                            "source_label": "情報連携学概論 I / 第08回 セキュリティ / security.pdf",
                            "source_type": "moocs_collect_slide_text",
                            "provider": "moocs_collect",
                            "excerpt": "暗号とセキュリティ",
                            "open_url": "/api/local/resources/local-resource%3Atest-1/file",
                        }
                    ],
                    "caution": "検索対象にはMOOCs-Collect由来テキストが含まれます。",
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
                    "chunks": [],
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
        self.assertEqual(3, report["task_count"])
        self.assertEqual(1, report["resource_count"])
        self.assertEqual(1, report["search_result_count"])
        self.assertEqual(1, report["material_context_count"])
        self.assertEqual("local-resource:test-1", report["detail_resource_id"])
        self.assertTrue(report["detail_checked"])

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
