"""The MCP stdio server: list_posts, get_thread and search over the MAF API.

Configured with MAF_TOKEN and MAF_URL. It runs on the user's machine, not the
server, and only reads.
"""

import asyncio
import json
import os
import urllib.parse
import urllib.request

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

TOKEN_ENV = "MAF_TOKEN"
URL_ENV = "MAF_URL"
DEFAULT_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 30


def api_get(path: str, params: dict | None = None) -> dict:
    token = os.environ.get(TOKEN_ENV)
    if not token:
        return {"error": f"{TOKEN_ENV} is not set"}
    base = os.environ.get(URL_ENV, DEFAULT_URL).rstrip("/")
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return {"error": f"HTTP {error.code}", "detail": error.read().decode()[:500]}
    except urllib.error.URLError as error:
        return {"error": f"could not reach MAF: {error.reason}"}


async def serve(reader, writer) -> None:
    async def list_tools(context, params) -> ListToolsResult:
        return ListToolsResult(tools=[
            Tool(
                name="list_posts",
                description="List MAF posts for a four-day window, newest first by default.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "before": {"type": "string", "description": "YYYY-MM-DD; the window ends the day before it"},
                        "sort": {"type": "string", "enum": ["new", "old", "views"]},
                    },
                },
            ),
            Tool(
                name="get_thread",
                description="Read one MAF post with its full comment tree.",
                inputSchema={
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "post id"}},
                    "required": ["id"],
                },
            ),
            Tool(
                name="search",
                description="Search MAF post titles, text and comments, 30 per page.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
            ),
        ])

    async def call_tool(context, params) -> CallToolResult:
        name, arguments = params.name, params.arguments or {}
        if name == "list_posts":
            result = api_get("/api/v1/posts", {"before": arguments.get("before"), "sort": arguments.get("sort")})
        elif name == "get_thread":
            result = api_get(f"/api/v1/threads/{arguments['id']}")
        elif name == "search":
            result = api_get("/api/v1/search", {"q": arguments["query"], "page": arguments.get("page")})
        else:
            result = {"error": f"unknown tool {name}"}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))])

    server = Server("maf", on_list_tools=list_tools, on_call_tool=call_tool)
    await server.run(reader, writer, server.create_initialization_options())


async def run() -> None:
    async with stdio_server() as (read, write):
        await serve(read, write)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
