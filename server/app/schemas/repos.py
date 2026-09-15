import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DeploymentSource = Literal["deployment", "release"]


class RepoResponse(BaseModel):
    id: uuid.UUID
    github_id: int
    full_name: str
    default_branch: str
    deployment_source: DeploymentSource
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateRepoRequest(BaseModel):
    deployment_source: DeploymentSource
