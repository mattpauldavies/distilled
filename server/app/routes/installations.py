"""Managing GitHub App installations per workspace.

The intent/claim pair implements the connect flow: an owner mints an intent
(the state nonce carried through GitHub's install redirect), then the setup
callback claims it. Claim is JWT-only — the workspace comes from the intent,
not from the active-workspace header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_auth, require_owner, require_user
from app.config import settings
from app.db import get_session
from app.models.user import User
from app.schemas.installation import (
    AvailableRepoResponse,
    AvailableReposResponse,
    ClaimRequest,
    ClaimResponse,
    InstallationsListResponse,
    InstallIntentResponse,
    WorkspaceInstallationResponse,
)
from app.services import installation_link_service
from app.services.installation_link_service import ClaimPending, IntentError, LinkError

router = APIRouter(prefix="/installations")


@router.post("/intents", response_model=InstallIntentResponse)
async def create_intent(
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> InstallIntentResponse:
    if not settings.github_app_slug:
        raise HTTPException(status_code=500, detail="GitHub App slug is not configured")
    nonce = await installation_link_service.create_intent(
        current.tenant_id, current.user_id, session
    )
    return InstallIntentResponse(
        install_url=(
            f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={nonce}"
        )
    )


@router.post("/claim", response_model=ClaimResponse)
async def claim(
    body: ClaimRequest,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> ClaimResponse | JSONResponse:
    try:
        tenant = await installation_link_service.claim_intent(
            body.state, body.installation_id, user, session
        )
    except ClaimPending:
        # Org installations bind via the webhook's verified sender; tell the
        # client to poll this endpoint until that lands.
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "pending"})
    except IntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.last_active_tenant_id = tenant.id
    await session.commit()
    return ClaimResponse(workspace_id=tenant.id, workspace_name=tenant.name)


@router.get("", response_model=InstallationsListResponse)
async def list_installations(
    current: CurrentUser = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> InstallationsListResponse:
    views = await installation_link_service.list_workspace_installations(
        current.tenant_id, session
    )
    return InstallationsListResponse(
        items=[
            WorkspaceInstallationResponse(
                installation_id=view.installation_id,
                account_login=view.account_login,
                account_type=view.account_type,
                repo_count=view.repo_count,
                removed=view.removed_at is not None,
            )
            for view in views
        ]
    )


@router.get("/{installation_id}/available-repos", response_model=AvailableReposResponse)
async def available_repos(
    installation_id: int,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> AvailableReposResponse:
    try:
        repos = await installation_link_service.list_available_repos(
            current.tenant_id, installation_id, session
        )
    except LinkError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AvailableReposResponse(
        items=[
            AvailableRepoResponse(
                github_id=repo.github_id,
                full_name=repo.full_name,
                default_branch=repo.default_branch,
                tracked=repo.tracked,
            )
            for repo in repos
        ]
    )


@router.delete("/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_installation(
    installation_id: int,
    current: CurrentUser = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await installation_link_service.unlink_installation(
            current.tenant_id, installation_id, session
        )
    except LinkError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
