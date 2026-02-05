# MCP-Client-Server

FastAPI backend with Anthropic Claude + in-process MCP tool registry for Taiga project management.

## Architecture

Single-process agent service:
- **FastAPI** HTTP server
- **Anthropic Claude** Messages API with tool use
- **In-process MCP** tool registry (no separate server)
- **Bounded multi-step loop** with budgets and idempotency
- **Role-based tool exposure** from Taiga permissions

## Setup

### Prerequisites

- Python 3.11+
- Anthropic API key
- Taiga account with API access

### Installation

```bash
pip install -r requirements.txt
```

### Environment Configuration

Create `.env` file:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

### Run Locally

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Server runs at `http://localhost:8000`

### Run with Docker

```bash
docker build -t mcp-backend .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key_here mcp-backend
```

## API

### POST /agent/run

Execute agent task.

**Request:**
```json
{
  "project_id": 1729875,
  "milestone_id": 499548,
  "user_story_id": 8909174,
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

### GET /health

Health check endpoint.

## Production Deployment (AWS EC2)

### 1. Provision EC2 Instance

Launch Ubuntu 22.04 LTS instance:
- Instance type: t3.small or larger
- Security group: Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS)
- Attach Elastic IP for static address

### 2. Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip -y

# Install nginx
sudo apt install nginx -y

# Install certbot for SSL
sudo apt install certbot python3-certbot-nginx -y
```

### 3. Deploy Application

```bash
# Clone repository
git clone <your-repo-url>
cd MCP-Client-Server

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
nano .env
# Add ANTHROPIC_API_KEY and ANTHROPIC_MODEL
```

### 4. Configure Domain & SSL

**Procure Domain:**
- Register domain via Route 53, Namecheap, or GoDaddy
- Point A record to EC2 Elastic IP

**Setup SSL with Certbot:**

```bash
# Configure nginx reverse proxy
sudo nano /etc/nginx/sites-available/mcp-backend

# Add configuration:
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/mcp-backend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Obtain SSL certificate
sudo certbot --nginx -d yourdomain.com

# Certbot auto-configures HTTPS redirect
```

### 5. Run with tmux

```bash
# Install tmux
sudo apt install tmux -y

# Start tmux session
tmux new -s mcp-backend

# Activate venv and run server
cd /path/to/MCP-Client-Server
source venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Detach from tmux: Ctrl+B, then D
# Reattach: tmux attach -t mcp-backend
```

### 6. Setup Systemd Service (Alternative to tmux)

```bash
sudo nano /etc/systemd/system/mcp-backend.service
```

```ini
[Unit]
Description=MCP Backend Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/MCP-Client-Server
Environment="PATH=/home/ubuntu/MCP-Client-Server/venv/bin"
EnvironmentFile=/home/ubuntu/MCP-Client-Server/.env
ExecStart=/home/ubuntu/MCP-Client-Server/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mcp-backend
sudo systemctl start mcp-backend
sudo systemctl status mcp-backend
```

## Tool Registry

Tools exposed based on Taiga role permissions:

**Read:**
- `taiga_get_project` (requires `view_project`)
- `taiga_list_milestones` (requires `view_milestones`)
- `taiga_get_milestone_by_name` (requires `view_milestones`)
- `taiga_list_user_stories` (requires `view_us`)

**Write:**
- `taiga_create_user_story` (requires `add_us`)
- `taiga_create_task` (requires `add_task`)

## Budgets & Safety

- `deadline_seconds`: 30
- `max_steps`: 10
- `max_total_tool_calls`: 25
- `max_write_calls`: 15
- `max_repeated_call_hash`: 2

Idempotency prevents duplicate writes. Loop detection stops infinite recursion.

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

## Resources

**FastAPI:**
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Uvicorn Server](https://www.uvicorn.org/)

**MCP (Model Context Protocol):**
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Specification](https://modelcontextprotocol.io/)

**Anthropic:**
- [Anthropic API Documentation](https://docs.anthropic.com/)
- [Claude Messages API](https://docs.anthropic.com/en/api/messages)
- [Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

**AWS:**
- [EC2 Getting Started](https://docs.aws.amazon.com/ec2/index.html)
- [Route 53 DNS](https://docs.aws.amazon.com/route53/)

**SSL/TLS:**
- [Certbot Documentation](https://certbot.eff.org/)
- [Let's Encrypt](https://letsencrypt.org/)

**Taiga:**
- [Taiga API Documentation](https://docs.taiga.io/api.html)

**System Tools:**
- [tmux Cheat Sheet](https://tmuxcheatsheet.com/)
- [systemd Service Management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
