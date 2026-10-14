"""MCP client smoke test over Streamable HTTP.
Usage: MCP_TOKEN=<token from POST /api/v1/auth/api-token> python scripts/mcp_smoke.py [url]"""
import asyncio
import json
import os
import sys

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/mcp"


async def main() -> None:
    headers = {"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}
    async with httpx2.AsyncClient(headers=headers, timeout=30) as http:
        async with streamable_http_client(URL, http_client=http) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("tools:", sorted(t.name for t in tools.tools))
                for name, args in [
                    ("get_org_info", {}),
                    ("aggregate_records", {"object_name": "Opportunity", "function": "SUM", "field": "Amount",
                                           "group_by": "StageName"}),
                    ("execute_soql", {"soql": "DELETE FROM Account"}),
                ]:
                    res = await session.call_tool(name, args)
                    text = res.content[0].text if res.content else json.dumps(res.structured_content)
                    print(f"\n{name}:", text[:400])


asyncio.run(main())
