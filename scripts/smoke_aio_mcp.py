"""Smoke-test INIAD-AIO MCP tools through the in-process JSON-RPC handler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.mcp.aio_server import (  # noqa: E402
    DEFAULT_BASE_URL,
    AioMcpClient,
    MinimalMcpServer,
)


DEFAULT_QUERY = "セキュリティ"
REQUIRED_TOOLS = {
    "list_tasks",
    "get_task_evidence",
    "list_local_resources",
    "search_local_resources",
    "get_local_resource",
}


class SmokeFailure(RuntimeError):
    """Raised when an MCP smoke check fails."""


def run_smoke(
    *,
    base_url: str = DEFAULT_BASE_URL,
    query: str = DEFAULT_QUERY,
    limit: int = 5,
    mode: str = "keyword",
    timeout_seconds: int = 10,
    session: Any | None = None,
    require_local_resources: bool = True,
    require_search_results: bool = True,
) -> dict[str, Any]:
    client = AioMcpClient(
        base_url=base_url,
        session=session,
        timeout_seconds=timeout_seconds,
    )
    server = MinimalMcpServer(client)

    initialize = _request_ok(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aio-mcp-smoke", "version": "1"},
            },
        },
    )
    tool_names = _tool_names(
        _request_ok(
            server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
    )
    missing_tools = sorted(REQUIRED_TOOLS - set(tool_names))
    if missing_tools:
        raise SmokeFailure(f"Missing MCP tools: {', '.join(missing_tools)}")

    tasks_payload = _tool_payload(
        server,
        3,
        "list_tasks",
        {},
    )
    task_count = _count_items(tasks_payload, "task_count", "items", "tasks")
    if task_count <= 0:
        raise SmokeFailure("list_tasks returned no tasks")

    resources_payload = _tool_payload(
        server,
        4,
        "list_local_resources",
        {},
    )
    resources = resources_payload.get("resources")
    if not isinstance(resources, list):
        raise SmokeFailure("list_local_resources did not return a resources array")
    if require_local_resources and not resources:
        raise SmokeFailure(
            "list_local_resources returned 0 resources. "
            "Build data/local/resource_index.json before the live smoke test."
        )

    search_payload = _tool_payload(
        server,
        5,
        "search_local_resources",
        {"query": query, "limit": limit, "mode": mode},
    )
    search_results = search_payload.get("results")
    if not isinstance(search_results, list):
        raise SmokeFailure("search_local_resources did not return a results array")
    if require_search_results and not search_results:
        raise SmokeFailure(
            f"search_local_resources({query!r}) returned 0 results. "
            "Use a query that exists in the local resource index."
        )

    detail_payload = None
    detail_resource_id = _first_resource_id(resources)
    if detail_resource_id is not None:
        detail_payload = _tool_payload(
            server,
            6,
            "get_local_resource",
            {"resource_id": detail_resource_id},
        )
        if not isinstance(detail_payload.get("resource"), dict):
            raise SmokeFailure("get_local_resource did not return a resource object")

    return {
        "status": "ok",
        "base_url": base_url,
        "server_info": initialize.get("serverInfo"),
        "tools": tool_names,
        "task_count": task_count,
        "resource_count": len(resources),
        "search_query": query,
        "search_mode": mode,
        "search_result_count": len(search_results),
        "detail_resource_id": detail_resource_id,
        "detail_checked": detail_payload is not None,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call INIAD-AIO MCP tools through JSON-RPC and verify that the "
            "running FastAPI backend returns task/resource data."
        )
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Running INIAD-AIO FastAPI base URL.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Local resource search query used for search_local_resources.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Search result limit.",
    )
    parser.add_argument(
        "--mode",
        choices=["keyword", "semantic", "hybrid"],
        default="keyword",
        help="Local resource search mode.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=10,
        help="HTTP timeout for FastAPI calls.",
    )
    parser.add_argument(
        "--allow-empty-local-resources",
        action="store_true",
        help="Do not fail when the local resource index has no resources.",
    )
    parser.add_argument(
        "--allow-empty-search",
        action="store_true",
        help="Do not fail when the search query has no results.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_smoke(
            base_url=args.base_url,
            query=args.query,
            limit=args.limit,
            mode=args.mode,
            timeout_seconds=args.timeout_seconds,
            require_local_resources=not args.allow_empty_local_resources,
            require_search_results=not args.allow_empty_search,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "detail": str(exc),
                    "base_url": args.base_url,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _request_ok(
    server: MinimalMcpServer,
    request: dict[str, Any],
) -> dict[str, Any]:
    response = server.handle_request(request)
    if response is None:
        raise SmokeFailure(f"Unexpected empty response for {request.get('method')}")
    if "error" in response:
        raise SmokeFailure(
            f"MCP request {request.get('method')} failed: {response['error']}"
        )
    result = response.get("result")
    if not isinstance(result, dict):
        raise SmokeFailure(f"MCP request {request.get('method')} returned no result")
    return result


def _tool_payload(
    server: MinimalMcpServer,
    request_id: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = _request_ok(
        server,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        },
    )
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{name} returned no structuredContent")
    return payload


def _tool_names(result: dict[str, Any]) -> list[str]:
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise SmokeFailure("tools/list returned no tools array")
    names = [str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)]
    return [name for name in names if name]


def _count_items(payload: dict[str, Any], count_key: str, *array_keys: str) -> int:
    count_value = payload.get(count_key)
    if isinstance(count_value, int):
        return count_value
    for key in array_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _first_resource_id(resources: list[Any]) -> str | None:
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource_id = str(resource.get("resource_id") or "").strip()
        if resource_id:
            return resource_id
    return None


if __name__ == "__main__":
    raise SystemExit(main())
