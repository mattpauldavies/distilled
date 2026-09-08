"""Tenant invitation lifecycle: create, revoke, resend, redeem.

Tokens are opaque 32-byte URL-safe strings. Only their SHA-256 hash is stored
— the raw token leaves the server exactly once, in the email body. Redemption
matches by hash, so a leaked DB does not enable invitation theft.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user import User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class InvitationError(Exception):
    pass


class DuplicateInvitationError(InvitationError):
    """An open invitation already exists for this (tenant, email)."""


class AlreadyMemberError(InvitationError):
    """The invitee is already a member of the tenant."""


class InvitationStateError(InvitationError):
    """The invitation is not in a redeemable state (expired, revoked, redeemed, unknown)."""


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_accept_url(token: str) -> str:
    base = (settings.app_base_url or "").rstrip("/")
    return f"{base}/invitations/accept?token={token}"


async def _existing_member_for_email(
    tenant_id: uuid.UUID, email: str, session: AsyncSession
) -> TenantUser | None:
    """A user with this email AND a membership in this tenant already exists."""
    result = await session.execute(
        select(TenantUser)
        .join(User, User.id == TenantUser.user_id)
        .where(TenantUser.tenant_id == tenant_id, func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def _open_invitation_for(
    tenant_id: uuid.UUID, email: str, session: AsyncSession
) -> Invitation | None:
    result = await session.execute(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id,
            Invitation.email == email,
            Invitation.redeemed_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _load_tenant(tenant_id: uuid.UUID, session: AsyncSession) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def create_invitation(
    *,
    tenant_id: uuid.UUID,
    inviter_user_id: uuid.UUID,
    inviter_display_name: str,
    email: str,
    session: AsyncSession,
    email_service: EmailService,
) -> Invitation:
    if await _existing_member_for_email(tenant_id, email, session) is not None:
        raise AlreadyMemberError(f"{email} is already a member")
    if await _open_invitation_for(tenant_id, email, session) is not None:
        raise DuplicateInvitationError(f"An open invitation for {email} already exists")

    tenant = await _load_tenant(tenant_id, session)
    if tenant is None:
        raise InvitationStateError(f"Tenant {tenant_id} does not exist")

    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        invited_by_user_id=inviter_user_id,
        email=email,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.invitation_ttl_days),
    )
    session.add(invitation)
    await session.flush()
    await session.commit()

    await email_service.send_invitation(
        to=email,
        tenant_name=tenant.name,
        inviter_name=inviter_display_name,
        accept_url=_build_accept_url(raw_token),
    )
    return invitation


async def revoke_invitation(
    *, invitation_id: uuid.UUID, tenant_id: uuid.UUID, session: AsyncSession
) -> None:
    """Mark a pending invitation as revoked. Idempotent."""
    result = await session.execute(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.tenant_id == tenant_id
        )
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise InvitationStateError("Invitation not found")
    if inv.revoked_at is not None:
        return  # idempotent
    if inv.redeemed_at is not None:
        raise InvitationStateError("Invitation has already been redeemed")
    inv.revoked_at = datetime.now(UTC)
    await session.commit()


async def resend_invitation(
    *,
    invitation_id: uuid.UUID,
    tenant_id: uuid.UUID,
    inviter_display_name: str,
    session: AsyncSession,
    email_service: EmailService,
) -> Invitation:
    """Rotate the token, reset the expiry, send a fresh email."""
    result = await session.execute(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.tenant_id == tenant_id
        )
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise InvitationStateError("Invitation not found")
    if inv.redeemed_at is not None or inv.revoked_at is not None:
        raise InvitationStateError("Cannot resend a redeemed or revoked invitation")

    tenant = await _load_tenant(tenant_id, session)
    if tenant is None:
        raise InvitationStateError(f"Tenant {tenant_id} does not exist")

    raw_token = secrets.token_urlsafe(32)
    inv.token_hash = _hash_token(raw_token)
    inv.expires_at = datetime.now(UTC) + timedelta(days=settings.invitation_ttl_days)
    await session.commit()

    await email_service.send_invitation(
        to=inv.email,
        tenant_name=tenant.name,
        inviter_name=inviter_display_name,
        accept_url=_build_accept_url(raw_token),
    )
    return inv


async def redeem_invitation(
    *, token: str, current_user_id: uuid.UUID, session: AsyncSession
) -> uuid.UUID:
    """Consume a token: add the current user as a member, return the joined tenant_id.

    Idempotent on (tenant, user): if the user is already a member, the invite
    is still marked redeemed but no new membership row is created.
    """
    result = await session.execute(
        select(Invitation).where(Invitation.token_hash == _hash_token(token))
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise InvitationStateError("Unknown invitation token")
    if inv.revoked_at is not None:
        raise InvitationStateError("Invitation has been revoked")
    if inv.redeemed_at is not None:
        raise InvitationStateError("Invitation has already been redeemed")
    if inv.expires_at < datetime.now(UTC):
        raise InvitationStateError("Invitation has expired")

    existing = await session.execute(
        select(TenantUser).where(
            TenantUser.tenant_id == inv.tenant_id, TenantUser.user_id == current_user_id
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(
            TenantUser(
                id=uuid.uuid4(),
                tenant_id=inv.tenant_id,
                user_id=current_user_id,
                role="member",
            )
        )

    inv.redeemed_at = datetime.now(UTC)
    await session.commit()
    return inv.tenant_id


async def list_pending_for_tenant(
    *, tenant_id: uuid.UUID, session: AsyncSession
) -> list[Invitation]:
    result = await session.execute(
        select(Invitation)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.redeemed_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


async def list_pending_for_user_emails(
    emails: list[str], *, session: AsyncSession
) -> list[Invitation]:
    """Find pending invitations whose email matches any of the user's verified emails."""
    if not emails:
        return []
    lowered = [e.lower() for e in emails if e]
    result = await session.execute(
        select(Invitation)
        .where(
            or_(*[func.lower(Invitation.email) == e for e in lowered]),
            Invitation.redeemed_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


async def expire_old_invitations(*, session: AsyncSession) -> int:
    """Mark expired-but-otherwise-open invitations as revoked.

    Inline expiry checks at redemption already enforce correctness; this is a
    janitor for the team page so stale rows don't pile up forever.
    """
    stmt = (
        update(Invitation)
        .where(
            Invitation.expires_at < datetime.now(UTC),
            Invitation.redeemed_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    result = await session.execute(stmt)
    await session.commit()
    return getattr(result, "rowcount", 0) or 0
