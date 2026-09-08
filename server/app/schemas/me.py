import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Role = Literal["owner", "member"]


class TenantMembershipResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
    role: Role


class TenantsListResponse(BaseModel):
    items: list[TenantMembershipResponse]


class MyInvitationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    inviter_name: str | None
    expires_at: datetime


class MyInvitationsListResponse(BaseModel):
    items: list[MyInvitationResponse]


class SetActiveTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class RedeemRequest(BaseModel):
    token: str


class RedeemResponse(BaseModel):
    tenant_id: uuid.UUID
