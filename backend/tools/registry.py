from typing import Dict, Any, List, Set, Callable, Optional
from dataclasses import dataclass
from backend.permissions.permissions import TAIGA_ROLE_PERMISSIONS
from backend.tools.taiga import TaigaClient
from backend.utils.errors import PermissionDeniedError
from backend.utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    required_permissions: Set[str]
    handler: Callable

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_tools()
    
    def _register_tools(self):
        """Register all Taiga tools"""
        
        # Read tools
        self.register(Tool(
            name="taiga_get_project",
            description="Get project details by slug or ID",
            input_schema={
                "type": "object",
                "properties": {
                    "project_ref": {"type": "string", "description": "Project slug or ID"}
                },
                "required": ["project_ref"]
            },
            required_permissions={"view_project"},
            handler=self._handle_get_project
        ))
        
        self.register(Tool(
            name="taiga_list_milestones",
            description="List all milestones (sprints) for a project",
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "Project ID"}
                },
                "required": ["project_id"]
            },
            required_permissions={"view_milestones"},
            handler=self._handle_list_milestones
        ))
        
        self.register(Tool(
            name="taiga_get_milestone_by_name",
            description="Find a milestone by name (e.g., 'Sprint 6')",
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "Project ID"},
                    "sprint_ref": {"type": "string", "description": "Sprint name"}
                },
                "required": ["project_id", "sprint_ref"]
            },
            required_permissions={"view_milestones"},
            handler=self._handle_get_milestone_by_name
        ))
        
        self.register(Tool(
            name="taiga_list_user_stories",
            description="List user stories, optionally filtered by milestone",
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "Project ID"},
                    "milestone_id": {"type": "integer", "description": "Optional milestone ID filter"}
                },
                "required": ["project_id"]
            },
            required_permissions={"view_us"},
            handler=self._handle_list_user_stories
        ))
        
        # Write tools
        self.register(Tool(
            name="taiga_create_user_story",
            description="Create a new user story",
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "Project ID"},
                    "subject": {"type": "string", "description": "User story title"},
                    "description": {"type": "string", "description": "User story description"},
                    "milestone_id": {"type": "integer", "description": "Optional milestone ID"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
                    "idempotency_key": {"type": "string", "description": "Idempotency key"}
                },
                "required": ["project_id", "subject", "idempotency_key"]
            },
            required_permissions={"add_us"},
            handler=self._handle_create_user_story
        ))
        
        self.register(Tool(
            name="taiga_create_task",
            description="Create a new task for a user story",
            input_schema={
                "type": "object",
                "properties": {
                    "user_story_id": {"type": "integer", "description": "User story ID"},
                    "subject": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Task description"},
                    "project_id": {"type": "integer", "description": "Project ID"},
                    "idempotency_key": {"type": "string", "description": "Idempotency key"}
                },
                "required": ["user_story_id", "subject", "idempotency_key"]
            },
            required_permissions={"add_task"},
            handler=self._handle_create_task
        ))
    
    def register(self, tool: Tool):
        self.tools[tool.name] = tool
    
    def list_tools(self, user_permissions: Set[str]) -> List[Dict[str, Any]]:
        """Return tool schemas filtered by permissions"""
        allowed = []
        for tool in self.tools.values():
            if tool.required_permissions.issubset(user_permissions):
                allowed.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema
                })
        logger.info(f"Exposed {len(allowed)}/{len(self.tools)} tools based on permissions")
        return allowed
    
    def call_tool(
        self,
        name: str,
        args: Dict[str, Any],
        user_permissions: Set[str],
        taiga_client: TaigaClient,
        idempotency_cache: Dict[str, Any]
    ) -> Any:
        """Execute a tool call with permission check"""
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        
        tool = self.tools[name]
        
        if not tool.required_permissions.issubset(user_permissions):
            raise PermissionDeniedError(f"Missing permissions for {name}")
        
        # Check idempotency cache for write operations
        idempotency_key = args.get("idempotency_key")
        if idempotency_key and idempotency_key in idempotency_cache:
            logger.info(f"Returning cached result for {idempotency_key}")
            return idempotency_cache[idempotency_key]
        
        result = tool.handler(taiga_client, args)
        
        # Cache write results
        if idempotency_key:
            idempotency_cache[idempotency_key] = result
        
        return result
    
    # Tool handlers
    def _handle_get_project(self, client: TaigaClient, args: Dict[str, Any]) -> Dict[str, Any]:
        project = client.get_project(args["project_ref"])
        return {"id": project.id, "name": project.name, "slug": project.slug}
    
    def _handle_list_milestones(self, client: TaigaClient, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        milestones = client.list_milestones(args["project_id"])
        return [{"id": m.id, "name": m.name, "project": m.project} for m in milestones]
    
    def _handle_get_milestone_by_name(self, client: TaigaClient, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        milestone = client.get_milestone_by_name(args["project_id"], args["sprint_ref"])
        if milestone:
            return {"id": milestone.id, "name": milestone.name, "project": milestone.project}
        return None
    
    def _handle_list_user_stories(self, client: TaigaClient, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        stories = client.list_user_stories(args["project_id"], args.get("milestone_id"))
        return [
            {
                "id": us.id,
                "subject": us.subject,
                "description": us.description,
                "milestone": us.milestone,
                "tags": us.tags
            }
            for us in stories
        ]
    
    def _handle_create_user_story(self, client: TaigaClient, args: Dict[str, Any]) -> Dict[str, Any]:
        us = client.create_user_story(
            project_id=args["project_id"],
            subject=args["subject"],
            description=args.get("description", ""),
            milestone_id=args.get("milestone_id"),
            tags=args.get("tags")
        )
        return {
            "id": us.id,
            "subject": us.subject,
            "description": us.description,
            "milestone": us.milestone,
            "tags": us.tags
        }
    
    def _handle_create_task(self, client: TaigaClient, args: Dict[str, Any]) -> Dict[str, Any]:
        task = client.create_task(
            user_story_id=args["user_story_id"],
            subject=args["subject"],
            description=args.get("description", ""),
            project_id=args.get("project_id")
        )
        return {
            "id": task.id,
            "subject": task.subject,
            "description": task.description,
            "user_story": task.user_story
        }

def get_user_permissions(roles: List[str]) -> Set[str]:
    """Compute permission set from user roles"""
    permissions = set()
    for role in roles:
        role_key = role.lower().replace(" ", "-")
        if role_key in TAIGA_ROLE_PERMISSIONS:
            permissions.update(TAIGA_ROLE_PERMISSIONS[role_key])
    return permissions
