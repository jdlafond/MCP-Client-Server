from pydantic import BaseModel
from typing import Optional, List

class TaigaProject(BaseModel):
    id: int
    name: str
    slug: str

class TaigaMilestone(BaseModel):
    id: int
    name: str
    project: int

class TaigaUserStory(BaseModel):
    id: int
    subject: str
    description: Optional[str] = None
    project: int
    milestone: Optional[int] = None
    tags: List[str] = []

class TaigaTask(BaseModel):
    id: int
    subject: str
    description: Optional[str] = None
    user_story: int
