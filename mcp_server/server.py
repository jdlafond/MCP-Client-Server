#!/usr/bin/env python3
"""
MCP Server using official MCP SDK for Taiga tools.
"""
import asyncio
from typing import Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp_server.tools.registry import ToolRegistry, get_user_permissions
from mcp_server.tools.taiga import TaigaClient
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

# Global state
registry = ToolRegistry()
taiga_clients = {}
idempotency_caches = {}

app = Server("taiga-mcp-server")

@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available tools"""
    # Note: In real implementation, we'd need to pass user context
    # For now, return all tools (filtering happens on client side)
    all_permissions = set()
    tools_data = registry.list_tools(all_permissions)
    
    return [
        Tool(
            name=tool["name"],
            description=tool["description"],
            inputSchema=tool["input_schema"]
        )
        for tool in tools_data
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a tool call"""
    try:
        # Extract context from arguments
        auth_token = arguments.pop("auth_token", None)
        roles = arguments.pop("roles", [])
        session_id = arguments.pop("session_id", "default")
        
        if not auth_token:
            raise ValueError("auth_token required")
        
        # Get or create Taiga client for this session
        if session_id not in taiga_clients:
            taiga_clients[session_id] = TaigaClient(auth_token)
            idempotency_caches[session_id] = {}
        
        taiga_client = taiga_clients[session_id]
        idempotency_cache = idempotency_caches[session_id]
        user_permissions = get_user_permissions(roles)
        
        # Call tool
        result = registry.call_tool(
            name,
            arguments,
            user_permissions,
            taiga_client,
            idempotency_cache
        )
        
        return [TextContent(type="text", text=str(result))]
    
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="taiga-mcp-server",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
