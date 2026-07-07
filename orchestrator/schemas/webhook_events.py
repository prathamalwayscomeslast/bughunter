from pydantic import BaseModel
from typing import Optional

class Label(BaseModel):
    name: str

class Issue(BaseModel):
    number: int
    title: str
    body: Optional[str] = ""

class Repository(BaseModel):
    full_name: str

class Installation(BaseModel):
    id: int

class IssueLabeledPayload(BaseModel):
    action: str
    label: Optional[Label] = None
    issue: Issue
    repository: Repository
    installation: Installation