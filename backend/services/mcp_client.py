import asyncio
import uuid
from typing import Dict, Any, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from backend.utils.logging import get_logger

logger = get_logger(__name__)

class MCPClient:
    """Client for communicating with MCP server via stdio"""
    
    def __init__(self):
        self.session: ClientSession = None
        self.session_id = str(uuid.uuid4())
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server())
    
    async def _start_server(self):
        """Start MCP server as subprocess"""
        logger.info("Starting MCP server...")
        
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],
            env=None
        )
        
        self.stdio_transport = await stdio_client(server_params)
        self.read_stream, self.write_stream = self.stdio_transport
        self.session = ClientSession(self.read_stream, self.write_stream)
        
        await self.session.initialize()
        logger.info("MCP server initialized")
    
    def list_tools(self, roles: List[str]) -> List[Dict[str, Any]]:
        """Get list of available tools based on roles"""
        async def _list():
            result = await self.session.list_tools()
            # Filter tools based on roles (simplified - server should handle this)
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                for tool in result.tools
            ]
        
        return self._loop.run_until_complete(_list())
    
    def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        auth_token: str,
        roles: List[str]
    ) -> Any:
        """Execute a tool call"""
        async def _call():
            # Add context to arguments
            args_with_context = {
                **arguments,
                "auth_token": auth_token,
                "roles": roles,
                "session_id": self.session_id
            }
            
            result = await self.session.call_tool(name, args_with_context)
            
            # Extract text content from result
            if result.content and len(result.content) > 0:
                return result.content[0].text
            return "{}"
        
        result_str = self._loop.run_until_complete(_call())
        
        # Parse result if it's JSON
        try:
            import json
            return json.loads(result_str)
        except:
            return result_str
    
    def close(self):
        """Shutdown MCP server"""
        async def _close():
            if self.session:
                logger.info("Shutting down MCP server...")
                await self.session.close()
        
        if self.session:
            self._loop.run_until_complete(_close())
            self._loop.close()
