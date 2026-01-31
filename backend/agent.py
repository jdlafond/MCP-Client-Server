import time
import uuid
from typing import Dict, Any, List
from collections import defaultdict
from backend.services.anthropic_client import AnthropicClient
from backend.tools.registry import ToolRegistry, get_user_permissions
from backend.tools.taiga import TaigaClient
from backend.models.agent_models import AgentRequest, AgentResponse, Artifacts, UserStoryArtifact, TaskArtifact
from backend.utils.hashing import hash_tool_call
from backend.utils.errors import BudgetExceededError, LoopDetectedError
from backend.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an AI assistant that helps manage Taiga project management tasks.

You have access to tools for reading and creating user stories and tasks in Taiga.

When the user provides meeting minutes and asks you to create user stories and tasks:
1. First, get the project details
2. Find the target milestone (sprint) by name
3. Create user stories with clear subjects and descriptions
4. Create tasks for each user story

Be efficient and avoid redundant tool calls. Always use the idempotency_key parameter for write operations.
Provide a clear summary of what you created."""

class AgentOrchestrator:
    def __init__(
        self,
        deadline_seconds: int = 30,
        max_steps: int = 10,
        max_total_tool_calls: int = 25,
        max_write_calls: int = 15,
        max_repeated_call_hash: int = 2
    ):
        self.deadline_seconds = deadline_seconds
        self.max_steps = max_steps
        self.max_total_tool_calls = max_total_tool_calls
        self.max_write_calls = max_write_calls
        self.max_repeated_call_hash = max_repeated_call_hash
        
        self.anthropic = AnthropicClient()
        self.registry = ToolRegistry()
    
    def run(self, request: AgentRequest) -> AgentResponse:
        """Execute agent loop with budgets and dedupe"""
        start_time = time.time()
        warnings = []
        
        # Setup
        user_permissions = get_user_permissions(request.user_context.roles)
        taiga_client = TaigaClient(request.auth_token)
        tools = self.registry.list_tools(user_permissions)
        
        if not tools:
            return AgentResponse(
                summary="No tools available for your role",
                artifacts=Artifacts(),
                warnings=["User has no permissions"]
            )
        
        # Tracking
        idempotency_cache: Dict[str, Any] = {}
        call_hash_counts: Dict[str, int] = defaultdict(int)
        total_tool_calls = 0
        write_calls = 0
        
        # Message history
        messages = [{"role": "user", "content": request.prompt}]
        
        # Loop
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
                    system=SYSTEM_PROMPT
                )
                logger.info(f"Claude response: stop_reason={response['stop_reason']}, content_blocks={len(response['content'])}")
                for block in response['content']:
                    logger.info(f"Content block: {block}")
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
            
            # Process tool calls
            tool_results = []
            has_tool_use = False
            
            for content_block in response["content"]:
                if content_block.get("type") == "tool_use":
                    has_tool_use = True
                    tool_name = content_block["name"]
                    tool_input = content_block["input"]
                    tool_use_id = content_block["id"]
                    
                    # Add idempotency key for write operations
                    if "idempotency_key" in self.registry.tools[tool_name].input_schema["properties"]:
                        if "idempotency_key" not in tool_input:
                            tool_input["idempotency_key"] = str(uuid.uuid4())
                    
                    # Dedupe check
                    call_hash = hash_tool_call(tool_name, tool_input)
                    call_hash_counts[call_hash] += 1
                    
                    if call_hash_counts[call_hash] > self.max_repeated_call_hash:
                        warnings.append(f"Loop detected: {tool_name}")
                        raise LoopDetectedError(f"Repeated call: {tool_name}")
                    
                    # Write budget check
                    if tool_name.startswith("taiga_create"):
                        write_calls += 1
                        if write_calls > self.max_write_calls:
                            warnings.append("Max write calls exceeded")
                            raise BudgetExceededError("Write budget exceeded")
                    
                    total_tool_calls += 1
                    
                    # Execute tool
                    try:
                        logger.info(f"Calling tool: {tool_name}")
                        result = self.registry.call_tool(
                            tool_name,
                            tool_input,
                            user_permissions,
                            taiga_client,
                            idempotency_cache
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": str(result)
                        })
                    except Exception as e:
                        logger.error(f"Tool execution error: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error: {str(e)}",
                            "is_error": True
                        })
            
            if not has_tool_use:
                break
            
            # Add tool results to messages
            messages.append({"role": "user", "content": tool_results})
        
        taiga_client.close()
        
        # Extract summary and artifacts
        summary = self._extract_summary(messages)
        artifacts = self._extract_artifacts(idempotency_cache)
        
        return AgentResponse(
            summary=summary,
            artifacts=artifacts,
            warnings=warnings
        )
    
    def _extract_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Extract final summary from messages"""
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block["text"]
                    elif isinstance(block, str):
                        return block
        return "Task completed"
    
    def _extract_artifacts(self, idempotency_cache: Dict[str, Any]) -> Artifacts:
        """Extract created artifacts from cache"""
        user_stories_map: Dict[int, UserStoryArtifact] = {}
        milestone_id = None
        
        for result in idempotency_cache.values():
            if isinstance(result, dict):
                if "user_story" in result:  # Task
                    us_id = result["user_story"]
                    task = TaskArtifact(id=result["id"], subject=result["subject"])
                    if us_id in user_stories_map:
                        user_stories_map[us_id].tasks.append(task)
                elif "milestone" in result and result.get("milestone"):  # User story
                    us_id = result["id"]
                    milestone_id = result["milestone"]
                    if us_id not in user_stories_map:
                        user_stories_map[us_id] = UserStoryArtifact(
                            id=us_id,
                            subject=result["subject"],
                            tasks=[]
                        )
        
        return Artifacts(
            milestone_id=milestone_id,
            user_stories=list(user_stories_map.values())
        )
