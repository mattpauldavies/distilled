import uuid
from datetime import datetime

from pydantic import BaseModel


class PullRequestResponse(BaseModel):
    id: uuid.UUID
    repo_id: uuid.UUID
    number: int
    title: str
    base_ref: str
    merged_at: datetime
    author_login: str
    html_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeploymentSummary(BaseModel):
    id: uuid.UUID
    environment_name: str
    deployed_at: datetime
    commit_sha: str

    model_config = {"from_attributes": True}


class PullRequestDetailResponse(PullRequestResponse):
    deployment: DeploymentSummary | None = None
