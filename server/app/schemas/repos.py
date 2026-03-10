import uuid
from datetime import datetime

from pydantic import BaseModel


class RepoResponse(BaseModel):
    id: uuid.UUID
    github_id: int
    full_name: str
    default_branch: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_production: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateEnvironmentRequest(BaseModel):
    is_production: bool
