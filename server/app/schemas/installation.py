"""Schemas for installation-management endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class InstallIntentResponse(BaseModel):
    install_url: str


class ClaimRequest(BaseModel):
    installation_id: int
    state: str = Field(min_length=1, max_length=128)


class ClaimResponse(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str


class WorkspaceInstallationResponse(BaseModel):
    installation_id: int
    account_login: str
    account_type: str
    repo_count: int
    removed: bool


class InstallationsListResponse(BaseModel):
    items: list[WorkspaceInstallationResponse]


class AvailableRepoResponse(BaseModel):
    github_id: int
    full_name: str
    default_branch: str | None
    tracked: bool


class AvailableReposResponse(BaseModel):
    items: list[AvailableRepoResponse]


class AddReposRequest(BaseModel):
    installation_id: int
    github_ids: list[int] = Field(min_length=1, max_length=100)
