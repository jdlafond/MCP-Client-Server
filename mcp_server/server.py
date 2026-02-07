#!/usr/bin/env python3
"""
MCP Server with stdio transport for Taiga tools.
Reads JSON-RPC messages from stdin, writes responses to stdout.
"""
import sys
import json
from typing import Dict, Any
from mcp_server.tools.registry import ToolRegistry, get_user_permissions
from mcp_server.tools.taiga import TaigaClient
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

class MCPServer:
    def __init__(self):
        self.registry = ToolRegistry()
        self.taiga_clients: Dict[str, TaigaClient] = {}
        self.idempotency_caches: Dict[str, Dict[str, Any]] = {}
        
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_list_tools(params)
            elif method == "tools/call":
                result = self._handle_call_tool(params)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
        except Exception as e:
            logger.error(f"Error handling {method}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
    
    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request"""
        return {
            "protocolVersion": "1.0",
            "serverInfo": {
                "name": "taiga-mcp-server",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
            }
        }
    
    def _handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request"""
        roles = params.get("roles", [])
        user_permissions = get_user_permissions(roles)
        tools = self.registry.list_tools(user_permissions)
        
        return {"tools": tools}
    
    def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request"""
        name = params.get("name")
        arguments = params.get("arguments", {})
        auth_token = params.get("auth_token")
        roles = params.get("roles", [])
        session_id = params.get("session_id", "default")
        
        if not auth_token:
            raise ValueError("auth_token required")
        
        # Get or create Taiga client for this session
        if session_id not in self.taiga_clients:
            self.taiga_clients[session_id] = TaigaClient(auth_token)
            self.idempotency_caches[session_id] = {}
        
        taiga_client = self.taiga_clients[session_id]
        idempotency_cache = self.idempotency_caches[session_id]
        user_permissions = get_user_permissions(roles)
        
        result = self.registry.call_tool(
            name,
            arguments,
            user_permissions,
            taiga_client,
            idempotency_cache
        )
        
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    
    def run(self):
        """Main loop: read from stdin, write to stdout"""
        logger.info("MCP Server started, listening on stdin...")
        
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error"
                    }
                }
                print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    server = MCPServer()
    server.run()
