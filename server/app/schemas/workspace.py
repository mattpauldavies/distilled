"""Schemas for workspace lifecycle endpoints."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: Literal["owner", "member"]
