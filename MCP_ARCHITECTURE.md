# MCP Architecture Conversion - Complete

## What We Built

Converted the in-process tool execution to a proper MCP (Model Context Protocol) architecture using the official MCP SDK.

## Architecture

```
Mobile App
    ↓ HTTP POST /agent/run
FastAPI (backend/main.py)
    ↓ Python call
AgentOrchestrator (backend/agent.py)
    ↓ MCP SDK Client
MCPClient (backend/services/mcp_client.py)
    ↓ stdio transport (JSON-RPC)
MCP Server (mcp_server/server.py)
    ↓ Python call
ToolRegistry (mcp_server/tools/registry.py)
    ↓ Python call
TaigaClient (mcp_server/tools/taiga.py)
    ↓ HTTP
Taiga API
```

## Key Components

### Backend (FastAPI Process)
- **backend/main.py** - FastAPI HTTP endpoints
- **backend/agent.py** - LLM orchestration loop with budgets
- **backend/services/mcp_client.py** - MCP SDK client (stdio transport)
- **backend/models/agent_models.py** - Request/response models

### MCP Server (Separate Process)
- **mcp_server/server.py** - MCP SDK server with stdio transport
- **mcp_server/tools/registry.py** - Tool definitions and execution
- **mcp_server/tools/taiga.py** - Taiga API client
- **mcp_server/permissions/permissions.py** - Role-based permissions
- **mcp_server/models/taiga_models.py** - Taiga data models

## Communication Protocol

**Transport:** stdio (stdin/stdout pipes)
**Protocol:** MCP SDK handles JSON-RPC automatically
**Format:** MCP standard messages

### Client → Server
```
python
# List tools
await session.list_tools()

# Call tool
await session.call_tool(name, arguments)
```

### Server → Client
```
python
# Tool list response
list[Tool]

# Tool call response
CallToolResult with TextContent
```

## Benefits of MCP Architecture

1. **Process Isolation** - Server crash doesn't kill FastAPI
2. **Reusability** - MCP server can be used by other clients
3. **Security** - Clear boundary between user-facing and privileged operations
4. **Standard Protocol** - Uses official MCP SDK
5. **Scalability** - Can run multiple server instances

## Running the System

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Start FastAPI (spawns MCP server automatically)
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The MCP server is spawned as a subprocess when AgentOrchestrator initializes.

## Testing

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 123,
    "milestone_id": 456,
    "prompt": "Create user stories",
    "auth_token": "...",
    "refresh": "...",
    "user_context": {
      "id": 1,
      "username": "test",
      "email": "test@example.com",
      "roles": ["Back"]
    }
  }'
```

## Next Steps

- Add error handling for MCP server crashes
- Implement server health checks
- Add metrics/monitoring
- Consider running MCP server as systemd service for production
