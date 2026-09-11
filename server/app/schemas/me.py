import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Role = Literal["owner", "member"]


class WorkspaceMembershipResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
    role: Role


class WorkspacesListResponse(BaseModel):
    items: list[WorkspaceMembershipResponse]


class MyInvitationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    inviter_name: str | None
    expires_at: datetime


class MyInvitationsListResponse(BaseModel):
    items: list[MyInvitationResponse]


class SetActiveWorkspaceRequest(BaseModel):
    workspace_id: uuid.UUID


class RedeemRequest(BaseModel):
    token: str


class RedeemResponse(BaseModel):
    workspace_id: uuid.UUID
