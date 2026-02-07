from typing import Dict, Any, List, Optional
import httpx
from tenacity import retry, stop_after_attempt, retry_if_exception_type
from mcp_server.models.taiga_models import TaigaProject, TaigaMilestone, TaigaUserStory, TaigaTask
from mcp_server.utils.errors import TaigaError
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

TAIGA_BASE_URL = "https://api.taiga.io/api/v1"

class TaigaClient:
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        self.client = httpx.Client(timeout=10.0)
    
    @retry(stop=stop_after_attempt(2), retry=retry_if_exception_type(httpx.HTTPStatusError))
    def _get(self, endpoint: str) -> Any:
        try:
            response = self.client.get(f"{TAIGA_BASE_URL}{endpoint}", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Taiga GET {endpoint} failed: {e.response.status_code}")
            raise TaigaError(f"Taiga API error: {e.response.status_code}")
    
    @retry(stop=stop_after_attempt(2), retry=retry_if_exception_type(httpx.HTTPStatusError))
    def _post(self, endpoint: str, data: Dict[str, Any]) -> Any:
        try:
            response = self.client.post(f"{TAIGA_BASE_URL}{endpoint}", json=data, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Taiga POST {endpoint} failed: {e.response.status_code}")
            raise TaigaError(f"Taiga API error: {e.response.status_code}")
    
    def get_project(self, project_id: int) -> TaigaProject:
        """Get project by ID"""
        data = self._get(f"/projects/{project_id}")
        return TaigaProject(id=data["id"], name=data["name"], slug=data["slug"])
    
    def list_milestones(self, project_id: int) -> List[TaigaMilestone]:
        """List all milestones for a project"""
        data = self._get(f"/milestones?project={project_id}")
        return [TaigaMilestone(id=m["id"], name=m["name"], project=m["project"]) for m in data]
    
    def get_milestone(self, milestone_id: int) -> TaigaMilestone:
        """Get milestone by ID"""
        data = self._get(f"/milestones/{milestone_id}")
        return TaigaMilestone(id=data["id"], name=data["name"], project=data["project"])
    
    def list_user_stories(self, project_id: int, milestone_id: Optional[int] = None) -> List[TaigaUserStory]:
        """List user stories, optionally filtered by milestone"""
        endpoint = f"/userstories?project={project_id}"
        if milestone_id:
            endpoint += f"&milestone={milestone_id}"
        data = self._get(endpoint)
        return [
            TaigaUserStory(
                id=us["id"],
                subject=us["subject"],
                description=us.get("description"),
                project=us["project"],
                milestone=us.get("milestone"),
                tags=us.get("tags", [])
            )
            for us in data
        ]
    
    def create_user_story(
        self,
        project_id: int,
        subject: str,
        description: str = "",
        milestone_id: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> TaigaUserStory:
        """Create a new user story"""
        payload = {
            "project": project_id,
            "subject": subject,
            "description": description
        }
        if milestone_id:
            payload["milestone"] = milestone_id
        if tags:
            payload["tags"] = tags
        
        data = self._post("/userstories", payload)
        return TaigaUserStory(
            id=data["id"],
            subject=data["subject"],
            description=data.get("description"),
            project=data["project"],
            milestone=data.get("milestone"),
            tags=data.get("tags", [])
        )
    
    def create_task(
        self,
        user_story_id: int,
        subject: str,
        description: str = "",
        project_id: Optional[int] = None
    ) -> TaigaTask:
        """Create a new task for a user story"""
        payload = {
            "user_story": user_story_id,
            "subject": subject,
            "description": description
        }
        if project_id:
            payload["project"] = project_id
        
        data = self._post("/tasks", payload)
        return TaigaTask(
            id=data["id"],
            subject=data["subject"],
            description=data.get("description"),
            user_story=data["user_story"]
        )
    
    def close(self):
        self.client.close()
