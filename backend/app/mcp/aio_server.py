"""Minimal MCP server exposing INIAD-AIO local demo tools."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TASK_COURSE_CODES = ("COT101", "SEM101", "COT105")
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class AioMcpClient:
    base_url: str = DEFAULT_BASE_URL
    session: Any | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def _session(self) -> Any:
        return self.session or requests.Session()

    def _get_json(
        self,
        path: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        response = self._session().get(
            url,
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("AIO API returned a non-object JSON payload")
        return payload

    def list_tasks(self, course_codes: list[str] | None = None) -> dict[str, Any]:
        resolved_codes = course_codes or list(DEFAULT_TASK_COURSE_CODES)
        params = [("course_code", course_code) for course_code in resolved_codes]
        return self._get_json("/api/tasks", params=params)

    def get_task_evidence(
        self,
        task_id: str,
        course_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        params = None
        if course_codes:
            params = [("course_code", course_code) for course_code in course_codes]
        path = f"/api/tasks/{quote(task_id, safe='')}/evidence"
        return self._get_json(path, params=params)

    def list_local_resources(self) -> dict[str, Any]:
        return self._get_json("/api/local/resources")

    def search_local_resources(
        self,
        query: str,
        limit: int = 10,
        mode: str = "keyword",
    ) -> dict[str, Any]:
        return self._get_json(
            "/api/local/resources/search",
            params={"q": query, "limit": limit, "mode": mode},
        )

    def get_local_resource(self, resource_id: str) -> dict[str, Any]:
        path = f"/api/local/resources/{quote(resource_id, safe='')}"
        return self._get_json(path)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_tasks",
        "description": "List INIAD-AIO task items for COT101, SEM101, and COT105.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional course codes. Defaults to COT101, SEM101, COT105.",
                }
            },
        },
    },
    {
        "name": "get_task_evidence",
        "description": "Return evidence details for an INIAD-AIO task.",
        "inputSchema": {
            "type": "object",
            "required": ["task_id"],
            "properties": {
                "task_id": {"type": "string"},
                "course_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional course code hints.",
                },
            },
        },
    },
    {
        "name": "list_local_resources",
        "description": "List indexed local lecture PDF resources.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_local_resources",
        "description": "Search indexed local lecture resources by keyword, semantic, or hybrid mode.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "mode": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "default": "keyword",
                },
            },
        },
    },
    {
        "name": "get_local_resource",
        "description": "Return metadata and a text-cache summary for one local resource.",
        "inputSchema": {
            "type": "object",
            "required": ["resource_id"],
            "properties": {"resource_id": {"type": "string"}},
        },
    },
]


class MinimalMcpServer:
    def __init__(self, client: AioMcpClient) -> None:
        self.client = client

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "iniad-aio", "version": "1.1-experimental"},
                }
            elif method == "tools/list":
                result = {"tools": TOOL_DEFINITIONS}
            elif method == "tools/call":
                result = self._call_tool(params)
            elif method == "ping":
                result = {}
            elif method == "notifications/initialized":
                return None
            else:
                return self._error_response(request_id, -32601, f"Unknown method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return self._error_response(request_id, -32000, str(exc))

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")

        data = call_aio_tool(self.client, name, arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(data, ensure_ascii=False, indent=2),
                }
            ],
            "structuredContent": data,
        }

    @staticmethod
    def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def call_aio_tool(
    client: AioMcpClient,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if name == "list_tasks":
        return client.list_tasks(_string_list(arguments.get("course_codes")))
    if name == "get_task_evidence":
        task_id = _required_string(arguments, "task_id")
        return client.get_task_evidence(
            task_id,
            _string_list(arguments.get("course_codes")),
        )
    if name == "list_local_resources":
        return client.list_local_resources()
    if name == "search_local_resources":
        query = _required_string(arguments, "query")
        limit = int(arguments.get("limit") or 10)
        mode = str(arguments.get("mode") or "keyword")
        return client.search_local_resources(query=query, limit=limit, mode=mode)
    if name == "get_local_resource":
        resource_id = _required_string(arguments, "resource_id")
        return client.get_local_resource(resource_id)
    raise ValueError(f"Unknown tool: {name}")


def run_stdio_server(server: MinimalMcpServer) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            response = server.handle_request(request)
        except Exception as exc:
            response = MinimalMcpServer._error_response(None, -32700, str(exc))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the INIAD-AIO minimal MCP server.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Running INIAD-AIO FastAPI base URL.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run_stdio_server(MinimalMcpServer(AioMcpClient(base_url=args.base_url)))


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("course_codes must be an array")
    return [str(item).strip() for item in value if str(item).strip()]


if __name__ == "__main__":
    main()
