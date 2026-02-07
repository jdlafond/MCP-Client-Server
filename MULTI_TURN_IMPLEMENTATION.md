# Multi-Turn Conversation Implementation

## Overview

This document describes how to add multi-turn conversation support to the agent system, enabling the LLM to maintain context across multiple requests within a session.

## The Problem

### Current Architecture (Single-Turn)
```
Request 1: "Create tasks for Alex"
  ↓
Backend: [No history] → LLM → "Which Alex?"
  ↓
Response: "I found 3 users named Alex..."

Request 2: "Alex Smith"
  ↓
Backend: [No history] → LLM → "What about Alex Smith?"
  ↓
❌ LLM has no context from Request 1!
```

### With Multi-Turn Support
```
Request 1: {session_id: "abc123", prompt: "Create tasks for Alex"}
  ↓
Backend: Load history[abc123] → LLM → "Which Alex?"
  ↓
Cache: history[abc123] = [user: "Create tasks", assistant: "Which Alex?"]
  ↓
Response: "I found 3 users named Alex..."

Request 2: {session_id: "abc123", prompt: "Alex Smith"}
  ↓
Backend: Load history[abc123] → LLM sees previous context
  ↓
✅ LLM knows we're talking about the Alex question!
```

## Implementation Steps

### 1. Update Request Model

**File:** `backend/models/agent_models.py`

```
python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class AgentRequest(BaseModel):
    project_id: int
    milestone_id: int
    prompt: str
    auth_token: str
    refresh: str
    user_context: UserContext
    user_story_id: Optional[int] = None
    session_id: Optional[str] = None  # NEW: For multi-turn conversations
```

### 2. Create Session Cache Service

**File:** `backend/services/session_cache.py`

```
python
from typing import Dict, List, Any
from datetime import datetime, timedelta

class SessionCache:
    """In-memory session cache for conversation history"""
    
    def __init__(self, ttl_minutes: int = 30):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for session"""
        if session_id not in self.sessions:
            return []
        
        session = self.sessions[session_id]
        
        # Check if expired
        if datetime.now() - session["last_access"] > self.ttl:
            del self.sessions[session_id]
            return []
        
        return session["history"]
    
    def update_history(
        self, 
        session_id: str, 
        history: List[Dict[str, Any]]
    ):
        """Update conversation history for session"""
        self.sessions[session_id] = {
            "history": history,
            "last_access": datetime.now()
        }
    
    def clear_session(self, session_id: str):
        """Clear session history"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def cleanup_expired(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired = [
            sid for sid, session in self.sessions.items()
            if now - session["last_access"] > self.ttl
        ]
        for sid in expired:
            del self.sessions[sid]
```

### 3. Update Agent Orchestrator

**File:** `backend/agent.py`

```
python
class AgentOrchestrator:
    def __init__(
        self,
        session_cache: SessionCache = None,
        deadline_seconds: int = 30,
        max_steps: int = 10,
        max_total_tool_calls: int = 25,
        max_write_calls: int = 15,
        max_repeated_call_hash: int = 2
    ):
        self.session_cache = session_cache
        self.deadline_seconds = deadline_seconds
        self.max_steps = max_steps
        self.max_total_tool_calls = max_total_tool_calls
        self.max_write_calls = max_write_calls
        self.max_repeated_call_hash = max_repeated_call_hash
        
        self.anthropic = AnthropicClient()
        self.mcp_client = MCPClient()
    
    def run(self, request: AgentRequest) -> AgentResponse:
        """Execute agent loop with budgets and dedupe"""
        start_time = time.time()
        warnings = []
        
        # Setup
        tools = self.mcp_client.list_tools(request.user_context.roles)
        
        if not tools:
            return AgentResponse(
                summary="No tools available for your role",
                artifacts=Artifacts(),
                warnings=["User has no permissions"]
            )
        
        # Load existing conversation history if session_id provided
        if request.session_id and self.session_cache:
            previous_history = self.session_cache.get_history(request.session_id)
        else:
            previous_history = []
        
        # Start with previous history
        messages = previous_history.copy()
        
        # Add new user message
        messages.append({"role": "user", "content": request.prompt})
        
        # Tracking
        idempotency_cache: Dict[str, Any] = {}
        call_hash_counts: Dict[str, int] = defaultdict(int)
        total_tool_calls = 0
        write_calls = 0
        
        # Build system prompt with context
        system_prompt = f"""You are an AI assistant that helps manage Taiga project management tasks.

You have access to tools for reading and creating user stories and tasks in Taiga.

Context for this request:
- Project ID: {request.project_id}
- Milestone ID: {request.milestone_id}
- User Story ID: {request.user_story_id if request.user_story_id else 'Not specified'}
- Requester: {request.user_context.username} ({request.user_context.email})
- Requester roles: {', '.join(request.user_context.roles)}

When creating user stories and tasks, use the project_id and milestone_id provided above.
Be efficient and avoid redundant tool calls. If the user supplies a user story id they intend to modify that or its tasks.
Always use the idempotency_key parameter for write operations.
Provide a clear summary of what you created."""
        
        # Loop (existing logic)
        for step in range(self.max_steps):
            # Budget checks
            if time.time() - start_time > self.deadline_seconds:
                warnings.append("Deadline exceeded")
                break
            
            if total_tool_calls >= self.max_total_tool_calls:
                warnings.append("Max tool calls exceeded")
                break
            
            logger.info(f"Step {step + 1}/{self.max_steps}")
            
            # Call Claude
            try:
                response = self.anthropic.create_message(
                    messages=messages,
                    tools=tools,
                    system=system_prompt
                )
                logger.info(f"Claude response: stop_reason={response['stop_reason']}")
            except Exception as e:
                logger.error(f"Anthropic API error: {e}")
                warnings.append(f"LLM error: {str(e)}")
                break
            
            # Add assistant message
            messages.append({"role": "assistant", "content": response["content"]})
            
            # Check if done
            if response["stop_reason"] == "end_turn":
                logger.info("Agent completed without tool use")
                break
            
            # Process tool calls (existing logic)
            # ... tool execution loop ...
        
        # Save updated history
        if request.session_id and self.session_cache:
            self.session_cache.update_history(request.session_id, messages)
        
        self.mcp_client.close()
        
        # Extract summary and artifacts
        summary = self._extract_summary(messages)
        artifacts = self._extract_artifacts(idempotency_cache)
        
        return AgentResponse(
            summary=summary,
            artifacts=artifacts,
            warnings=warnings
        )
```

### 4. Update FastAPI Endpoint

**File:** `backend/main.py`

```
python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from backend.models.agent_models import AgentRequest, AgentResponse
from backend.agent import AgentOrchestrator
from backend.services.session_cache import SessionCache
from backend.utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)

app = FastAPI(title="MCP-Client-Server Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global session cache
session_cache = SessionCache(ttl_minutes=30)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/agent/run", response_model=AgentResponse)
def agent_run(request: AgentRequest):
    """Main agent endpoint with session support"""
    logger.info(f"Agent run request for project={request.project_id}, milestone={request.milestone_id}")
    if request.session_id:
        logger.info(f"Session ID: {request.session_id}")
    
    try:
        orchestrator = AgentOrchestrator(session_cache=session_cache)
        response = orchestrator.run(request)
        return response
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/agent/session/{session_id}")
def clear_session(session_id: str):
    """Clear conversation history for a session"""
    session_cache.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}

@app.post("/agent/session/cleanup")
def cleanup_sessions():
    """Manually trigger cleanup of expired sessions"""
    session_cache.cleanup_expired()
    return {"status": "cleaned"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Mobile App Integration

### First Request (Start Conversation)

```typescript
import { v4 as uuidv4 } from 'uuid';

// Generate session ID
const sessionId = uuidv4();

const response = await fetch('http://localhost:8000/agent/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,
    project_id: 1729875,
    milestone_id: 499548,
    prompt: "Create tasks for Alex",
    auth_token: "bearer_token",
    refresh: "refresh_token",
    user_context: {
      id: 738718,
      username: "jdlafond",
      email: "jdlafond@asu.edu",
      roles: ["Back", "Product Owner"]
    }
  })
});

const data = await response.json();
// Response: "I found 3 users named Alex. Which one?"

// Store sessionId for follow-up
await AsyncStorage.setItem('currentSessionId', sessionId);
```

### Follow-up Request (Continue Conversation)

```typescript
// Retrieve session ID
const sessionId = await AsyncStorage.getItem('currentSessionId');

const response = await fetch('http://localhost:8000/agent/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,  // Same session
    project_id: 1729875,
    milestone_id: 499548,
    prompt: "Alex Smith",  // LLM has context now
    auth_token: "bearer_token",
    refresh: "refresh_token",
    user_context: {
      id: 738718,
      username: "jdlafond",
      email: "jdlafond@asu.edu",
      roles: ["Back", "Product Owner"]
    }
  })
});

const data = await response.json();
// Response: "Created 3 tasks for Alex Smith"
```

### Clear Session (New Conversation)

```typescript
const sessionId = await AsyncStorage.getItem('currentSessionId');

await fetch(`http://localhost:8000/agent/session/${sessionId}`, {
  method: 'DELETE'
});

// Remove from storage
await AsyncStorage.removeItem('currentSessionId');
```

## Storage Options

### Option 1: In-Memory (Simple, Development)

**Pros:**
- Simple implementation
- Fast
- No external dependencies

**Cons:**
- Lost on server restart
- Not suitable for multi-instance deployments
- Limited by server memory

**Use case:** Development, single-server deployments

### Option 2: Redis (Production Recommended)

**File:** `backend/services/redis_session_cache.py`

```
python
import redis
import json
from typing import List, Dict, Any

class RedisSessionCache:
    def __init__(self, host='localhost', port=6379, ttl_seconds=1800):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)
        self.ttl = ttl_seconds
    
    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        data = self.redis.get(f"session:{session_id}")
        if data:
            return json.loads(data)
        return []
    
    def update_history(self, session_id: str, history: List[Dict[str, Any]]):
        self.redis.setex(
            f"session:{session_id}",
            self.ttl,
            json.dumps(history)
        )
    
    def clear_session(self, session_id: str):
        self.redis.delete(f"session:{session_id}")
```

**Pros:**
- Persistent across restarts
- Works with multiple server instances
- Fast
- Built-in TTL

**Cons:**
- Requires Redis server
- Additional infrastructure

**Use case:** Production deployments

### Option 3: Database (Long-term Storage)

**File:** `backend/services/db_session_cache.py`

```
python
from sqlalchemy import Column, String, Text, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

Base = declarative_base()

class ConversationSession(Base):
    __tablename__ = 'conversation_sessions'
    
    session_id = Column(String(36), primary_key=True)
    history = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_access = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DBSessionCache:
    def __init__(self, database_url: str):
        engine = create_engine(database_url)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.session = Session()
    
    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        record = self.session.query(ConversationSession).filter_by(
            session_id=session_id
        ).first()
        
        if record:
            return json.loads(record.history)
        return []
    
    def update_history(self, session_id: str, history: List[Dict[str, Any]]):
        record = self.session.query(ConversationSession).filter_by(
            session_id=session_id
        ).first()
        
        if record:
            record.history = json.dumps(history)
            record.last_access = datetime.utcnow()
        else:
            record = ConversationSession(
                session_id=session_id,
                history=json.dumps(history)
            )
            self.session.add(record)
        
        self.session.commit()
    
    def clear_session(self, session_id: str):
        self.session.query(ConversationSession).filter_by(
            session_id=session_id
        ).delete()
        self.session.commit()
```

**Pros:**
- Persistent
- Queryable for analytics
- Audit trail
- Can store metadata

**Cons:**
- Slower than Redis
- More complex
- Database overhead

**Use case:** Compliance, analytics, debugging

## Key Considerations

### 1. Token Limits

Conversation history grows with each turn. Need to manage token limits:

```
python
def truncate_history(
    history: List[Dict[str, Any]], 
    max_tokens: int = 10000
) -> List[Dict[str, Any]]:
    """Keep recent messages within token limit"""
    # Simple approach: keep last N messages
    # Better approach: Use tiktoken to count actual tokens
    
    if len(history) <= 10:
        return history
    
    # Keep first message (often contains important context)
    # Keep last 8 messages
    return [history[0]] + history[-8:]
```

### 2. Session Scope

Decide what a session represents:

```
python
# Option A: Per-user global session
session_id = f"user:{user_id}"

# Option B: Per-project session
session_id = f"user:{user_id}:project:{project_id}"

# Option C: Per-milestone session
session_id = f"user:{user_id}:project:{project_id}:milestone:{milestone_id}"

# Option D: Explicit user-controlled sessions (recommended)
session_id = uuid4()  # Mobile app manages lifecycle
```

### 3. Session Expiry

```python
# Typical TTL values
TTL_SHORT = 300      # 5 minutes - quick interactions
TTL_MEDIUM = 1800    # 30 minutes - standard chat
TTL_LONG = 3600      # 1 hour - complex workflows
```

### 4. Mobile App UX

**Conversation UI:**
```typescript
// Show conversation history
const [messages, setMessages] = useState([]);
const [sessionId, setSessionId] = useState(null);

// New conversation button
const startNewConversation = async () => {
  if (sessionId) {
    await clearSession(sessionId);
  }
  setSessionId(uuidv4());
  setMessages([]);
};

// Send message
const sendMessage = async (prompt: string) => {
  const response = await agentRun({
    session_id: sessionId,
    prompt,
    // ... other fields
  });
  
  setMessages([
    ...messages,
    { role: 'user', content: prompt },
    { role: 'assistant', content: response.summary }
  ]);
};
```

## When to Use Multi-Turn

### Use Multi-Turn When:
- User needs to refine ambiguous requests
- Exploratory workflows ("Show me options")
- Complex multi-step processes
- Natural conversation is valuable

### Don't Use Multi-Turn When:
- Requests are always complete and specific
- UI provides all necessary context
- Single-turn is faster and simpler
- Token costs are a concern

## Current Architecture Decision

**Your current implementation is stateless (single-turn).**

This is appropriate because:
- Mobile UI provides structured context (project, milestone selection)
- Prompts are typically complete ("Create 3 user stories for login")
- Simpler architecture
- Lower latency
- Lower costs

**Add multi-turn support only if:**
- Users frequently need clarification
- Conversational refinement adds value
- You're willing to manage session complexity

## Testing

```bash
# Test session creation
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "project_id": 1729875,
    "milestone_id": 499548,
    "prompt": "Create tasks for Alex",
    "auth_token": "...",
    "refresh": "...",
    "user_context": {...}
  }'

# Test session continuation
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "project_id": 1729875,
    "milestone_id": 499548,
    "prompt": "Alex Smith",
    "auth_token": "...",
    "refresh": "...",
    "user_context": {...}
  }'

# Clear session
curl -X DELETE http://localhost:8000/agent/session/test-session-123
```
