import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["mcp_server.py"],
)

async def mcp_call(tool_name: str, **kwargs):
    """Call a tool on the MCP server via stdio. Spawns the server process automatically."""
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=kwargs)
            
            if tool_name in ["search_job_descriptions", "get_placement_history"] and not result.content:
                return []
                
            if result.content and len(result.content) > 0:
                parsed_contents = []
                for content in result.content:
                    text = content.text
                    try:
                        parsed_contents.append(json.loads(text))
                    except json.JSONDecodeError:
                        parsed_contents.append(text)
                        
                if tool_name in ["search_job_descriptions", "get_placement_history"]:
                    return parsed_contents
                    
                if len(parsed_contents) == 1:
                    return parsed_contents[0]
                return parsed_contents
            return None