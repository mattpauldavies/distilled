"""Internal endpoints driven by Railway's scheduled job runner.

Authenticated by a shared bearer secret rather than user JWT — these are not
user-facing.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.services import invitation_service

router = APIRouter(prefix="/internal")
_bearer_scheme = HTTPBearer()


def _verify_cron_secret(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="cron secret not configured")
    if not hmac.compare_digest(credentials.credentials, settings.internal_cron_secret):
        raise HTTPException(status_code=401, detail="invalid authorization")


@router.post("/invitations/expire")
async def expire_invitations(
    _auth: None = Depends(_verify_cron_secret),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Janitor: mark expired-but-not-redeemed invitations as revoked.

    Inline expiry checks at redeem time are the correctness mechanism; this
    keeps the team page free of stale rows.
    """
    count = await invitation_service.expire_old_invitations(session=session)
    return {"expired": count}
