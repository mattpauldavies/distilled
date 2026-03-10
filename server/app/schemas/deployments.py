import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.pull_requests import PullRequestResponse


class DeploymentResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    environment_name: str
    deployment_id: int
    commit_sha: str
    ref: str
    deployed_at: datetime
    html_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeploymentDetailResponse(DeploymentResponse):
    attributed_prs: list[PullRequestResponse] = []
