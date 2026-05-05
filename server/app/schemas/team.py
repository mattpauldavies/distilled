import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["owner", "member"]


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str | None
    github_username: str | None
    role: Role


class PendingInvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    invited_at: datetime
    expires_at: datetime


class TenantSummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
    role: Role


class TeamResponse(BaseModel):
    tenant: TenantSummaryResponse
    rename_prompt_dismissed: bool
    members: list[MemberResponse]
    pending_invitations: list[PendingInvitationResponse]


class RenameTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    rename_prompt_dismissed: bool | None = None


class CreateInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class CreateInvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    expires_at: datetime
