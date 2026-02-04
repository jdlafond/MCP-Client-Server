from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class UserContext(BaseModel):
    id: int
    username: str
    email: str
    roles: List[str]

class AgentRequest(BaseModel):
    project_id: int
    milestone_id: int
    prompt: str
    auth_token: str
    refresh: str
    user_context: UserContext
    user_story_id: Optional[int] = None

class TaskArtifact(BaseModel):
    id: int
    subject: str

class UserStoryArtifact(BaseModel):
    id: int
    subject: str
    tasks: List[TaskArtifact] = []

class Artifacts(BaseModel):
    milestone_id: Optional[int] = None
    user_stories: List[UserStoryArtifact] = []

class AgentResponse(BaseModel):
    summary: str
    artifacts: Artifacts
    warnings: List[str] = []
