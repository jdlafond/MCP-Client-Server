# MCP-Client-Server Backend

FastAPI backend with Anthropic Claude + in-process MCP tool registry for Taiga.

## Architecture

- **FastAPI** HTTP server
- **Anthropic Claude** Messages API with tool use
- **In-process MCP** tool registry (no separate server)
- **Bounded multi-step loop** with budgets and dedupe
- **Role-based tool exposure** from Taiga permissions

## Setup

### Prerequisites

- Python 3.11+
- Anthropic API key
- Taiga account with API access

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env file with your API key and model
```

### Run Locally

```bash
# From repo root
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The `.env` file is automatically loaded. Server runs at `http://localhost:8000`

### Run with Docker

```bash
# Build
docker build -t mcp-backend .

# Run
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key_here mcp-backend
```

## API Endpoints

### GET /health

Health check.

**Response:**
```json
{"status": "ok"}
```

### POST /agent/run

Execute agent task.

**Request:**
```json
{
  "project_ref": "my-project",
  "sprint_ref": "Sprint 6",
  "prompt": "MEETING MINUTES...\n\nCreate user stories and tasks for Sprint 6.",
  "auth_token": "your_taiga_bearer_token",
  "refresh": "your_refresh_token",
  "user_context": {
    "id": 738718,
    "username": "jdlafond",
    "email": "jdlafond@asu.edu",
    "roles": ["Back", "Product Owner"]
  }
}
```

**Response:**
```json
{
  "summary": "Created 3 user stories and 9 tasks in Sprint 6.",
  "artifacts": {
    "milestone_id": 12345,
    "user_stories": [
      {
        "id": 111,
        "subject": "As a user, I can log workouts",
        "tasks": [
          {"id": 9001, "subject": "Create workout log screen"}
        ]
      }
    ]
  },
  "warnings": []
}
```

## Example cURL

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_ref": "my-project",
    "sprint_ref": "Sprint 6",
    "prompt": "Create a user story for login feature with 2 tasks",
    "auth_token": "YOUR_TAIGA_TOKEN",
    "refresh": "YOUR_REFRESH_TOKEN",
    "user_context": {
      "id": 1,
      "username": "test",
      "email": "test@example.com",
      "roles": ["Back"]
    }
  }'
```

## Tool Registry

Tools are exposed based on Taiga role permissions:

**Read tools:**
- `taiga_get_project` (requires `view_project`)
- `taiga_list_milestones` (requires `view_milestones`)
- `taiga_get_milestone_by_name` (requires `view_milestones`)
- `taiga_list_user_stories` (requires `view_us`)

**Write tools:**
- `taiga_create_user_story` (requires `add_us`)
- `taiga_create_task` (requires `add_task`)

## Budgets

- `deadline_seconds`: 30
- `max_steps`: 10
- `max_total_tool_calls`: 25
- `max_write_calls`: 15
- `max_repeated_call_hash`: 2

## Project Structure

```
backend/
├── main.py              # FastAPI app
├── agent.py             # Orchestrator loop
├── models/
│   ├── agent_models.py  # Request/response types
│   └── taiga_models.py  # Taiga DTOs
├── services/
│   ├── anthropic_client.py
│   └── http_client.py
├── tools/
│   ├── registry.py      # Tool registration + gating
│   └── taiga.py         # Taiga API client
├── permissions/
│   └── permissions.py   # Role → permission mapping
└── utils/
    ├── errors.py
    ├── hashing.py
    └── logging.py
```

## Development

Run tests (when implemented):
```bash
pytest
```

Format code:
```bash
black backend/
```

## Notes

- Auth tokens are never logged
- Idempotency prevents duplicate writes
- Loop detection stops infinite recursion
- Partial results returned on budget exhaustion
