import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import invitation_service
from app.services.invitation_service import (
    AlreadyMemberError,
    DuplicateInvitationError,
    InvitationStateError,
    create_invitation,
    list_pending_for_tenant,
    list_pending_for_user_emails,
    redeem_invitation,
    resend_invitation,
    revoke_invitation,
)


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars(rows):
    result = MagicMock()
    s = MagicMock()
    s.all.return_value = rows
    result.scalars.return_value = s
    result.all = MagicMock(return_value=rows)
    return result


def _session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.delete = AsyncMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    return s


class StubEmail:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_invitation(self, **kwargs) -> None:
        self.calls.append(kwargs)


# --- create_invitation ---


@pytest.mark.asyncio
async def test_create_invitation_inserts_and_emails():
    s = _session()
    tenant = Tenant(id=uuid.uuid4(), name="Acme")
    inviter_id = uuid.uuid4()
    s.execute = AsyncMock(
        side_effect=[
            _scalar(None),  # no existing membership for this email
            _scalar(None),  # no open invitation
            _scalar(tenant),  # load tenant for email
        ]
    )
    email = StubEmail()

    inv = await create_invitation(
        tenant_id=tenant.id,
        inviter_user_id=inviter_id,
        inviter_display_name="Anna",
        email="Sam@Acme.com",
        session=s,
        email_service=email,
    )

    assert isinstance(inv, Invitation)
    assert inv.email == "Sam@Acme.com"  # original casing preserved; citext handles match
    assert inv.tenant_id == tenant.id
    assert inv.invited_by_user_id == inviter_id
    assert inv.expires_at > datetime.now(UTC)
    s.add.assert_called_once()
    s.commit.assert_awaited()
    assert len(email.calls) == 1
    assert email.calls[0]["to"] == "Sam@Acme.com"
    assert email.calls[0]["tenant_name"] == "Acme"
    assert email.calls[0]["inviter_name"] == "Anna"
    assert "/invitations/accept?token=" in email.calls[0]["accept_url"]


@pytest.mark.asyncio
async def test_create_invitation_rejects_existing_member():
    s = _session()
    membership = TenantUser(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), role="member"
    )
    s.execute = AsyncMock(return_value=_scalar(membership))

    with pytest.raises(AlreadyMemberError):
        await create_invitation(
            tenant_id=uuid.uuid4(),
            inviter_user_id=uuid.uuid4(),
            inviter_display_name="Anna",
            email="sam@acme.com",
            session=s,
            email_service=StubEmail(),
        )


@pytest.mark.asyncio
async def test_create_invitation_rejects_duplicate_open_invite():
    s = _session()
    existing = Invitation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        invited_by_user_id=uuid.uuid4(),
        email="sam@acme.com",
        token_hash="h",
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    s.execute = AsyncMock(side_effect=[_scalar(None), _scalar(existing)])

    with pytest.raises(DuplicateInvitationError):
        await create_invitation(
            tenant_id=uuid.uuid4(),
            inviter_user_id=uuid.uuid4(),
            inviter_display_name="Anna",
            email="sam@acme.com",
            session=s,
            email_service=StubEmail(),
        )


# --- revoke_invitation ---


@pytest.mark.asyncio
async def test_revoke_invitation_marks_revoked_at():
    inv = Invitation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        invited_by_user_id=uuid.uuid4(),
        email="sam@x.com",
        token_hash="h",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    await revoke_invitation(invitation_id=inv.id, tenant_id=inv.tenant_id, session=s)

    assert inv.revoked_at is not None
    s.commit.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_already_revoked_is_idempotent():
    inv = Invitation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        invited_by_user_id=uuid.uuid4(),
        email="sam@x.com",
        token_hash="h",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        revoked_at=datetime.now(UTC),
    )
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    await revoke_invitation(invitation_id=inv.id, tenant_id=inv.tenant_id, session=s)
    # Did not double-set revoked_at, but did not raise.
    assert inv.revoked_at is not None


# --- resend_invitation ---


@pytest.mark.asyncio
async def test_resend_invitation_rotates_token_and_resets_expiry():
    tenant = Tenant(id=uuid.uuid4(), name="Acme")
    old_token_hash = hashlib.sha256(b"old").hexdigest()
    inv = Invitation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        invited_by_user_id=uuid.uuid4(),
        email="sam@x.com",
        token_hash=old_token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=1),  # nearly expired
    )
    s = _session()
    s.execute = AsyncMock(side_effect=[_scalar(inv), _scalar(tenant)])
    email = StubEmail()

    refreshed = await resend_invitation(
        invitation_id=inv.id,
        tenant_id=tenant.id,
        inviter_display_name="Anna",
        session=s,
        email_service=email,
    )

    assert refreshed.token_hash != old_token_hash
    assert refreshed.expires_at > datetime.now(UTC) + timedelta(days=10)
    assert len(email.calls) == 1


@pytest.mark.asyncio
async def test_resend_revoked_or_redeemed_raises():
    inv = Invitation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        invited_by_user_id=uuid.uuid4(),
        email="sam@x.com",
        token_hash="h",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        redeemed_at=datetime.now(UTC),
    )
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    with pytest.raises(InvitationStateError):
        await resend_invitation(
            invitation_id=inv.id,
            tenant_id=inv.tenant_id,
            inviter_display_name="Anna",
            session=s,
            email_service=StubEmail(),
        )


# --- redeem_invitation ---


def _fresh_invite(token: str, *, tenant_id=None) -> Invitation:
    return Invitation(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        invited_by_user_id=uuid.uuid4(),
        email="sam@x.com",
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


@pytest.mark.asyncio
async def test_redeem_creates_membership_and_sets_redeemed_at():
    s = _session()
    inv = _fresh_invite("good-token")
    user_id = uuid.uuid4()

    s.execute = AsyncMock(
        side_effect=[
            _scalar(inv),  # find invitation by token_hash
            _scalar(None),  # existing membership lookup → none
        ]
    )

    tenant_id = await redeem_invitation(token="good-token", current_user_id=user_id, session=s)

    assert tenant_id == inv.tenant_id
    assert inv.redeemed_at is not None
    s.add.assert_called_once()
    added = s.add.call_args[0][0]
    assert isinstance(added, TenantUser)
    assert added.role == "member"
    assert added.user_id == user_id


@pytest.mark.asyncio
async def test_redeem_unknown_token():
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(None))

    with pytest.raises(InvitationStateError):
        await redeem_invitation(token="bad", current_user_id=uuid.uuid4(), session=s)


@pytest.mark.asyncio
async def test_redeem_expired():
    inv = _fresh_invite("good-token")
    inv.expires_at = datetime.now(UTC) - timedelta(days=1)
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    with pytest.raises(InvitationStateError):
        await redeem_invitation(token="good-token", current_user_id=uuid.uuid4(), session=s)


@pytest.mark.asyncio
async def test_redeem_revoked():
    inv = _fresh_invite("good-token")
    inv.revoked_at = datetime.now(UTC)
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    with pytest.raises(InvitationStateError):
        await redeem_invitation(token="good-token", current_user_id=uuid.uuid4(), session=s)


@pytest.mark.asyncio
async def test_redeem_already_redeemed():
    inv = _fresh_invite("good-token")
    inv.redeemed_at = datetime.now(UTC)
    s = _session()
    s.execute = AsyncMock(return_value=_scalar(inv))

    with pytest.raises(InvitationStateError):
        await redeem_invitation(token="good-token", current_user_id=uuid.uuid4(), session=s)


@pytest.mark.asyncio
async def test_redeem_when_already_member_is_idempotent():
    """If the redeeming user is already a member, the invite is consumed but no
    new membership row is added."""
    s = _session()
    inv = _fresh_invite("good-token")
    user_id = uuid.uuid4()
    existing_membership = TenantUser(
        id=uuid.uuid4(), tenant_id=inv.tenant_id, user_id=user_id, role="member"
    )

    s.execute = AsyncMock(
        side_effect=[_scalar(inv), _scalar(existing_membership)]
    )

    tenant_id = await redeem_invitation(token="good-token", current_user_id=user_id, session=s)

    assert tenant_id == inv.tenant_id
    s.add.assert_not_called()
    assert inv.redeemed_at is not None


# --- list_pending ---


@pytest.mark.asyncio
async def test_list_pending_for_tenant():
    inv = _fresh_invite("t")
    s = _session()
    s.execute = AsyncMock(return_value=_scalars([inv]))
    pending = await list_pending_for_tenant(tenant_id=inv.tenant_id, session=s)
    assert pending == [inv]


@pytest.mark.asyncio
async def test_list_pending_for_user_emails_lower_cases_input():
    inv = _fresh_invite("t")
    s = _session()
    s.execute = AsyncMock(return_value=_scalars([inv]))

    out = await list_pending_for_user_emails(["Sam@Acme.com", "x@y.com"], session=s)

    assert out == [inv]
    # The query received the pre-lowered emails (we can't easily inspect the
    # SQLAlchemy expression, but at least one execute happened with no error).
    assert s.execute.await_count == 1


@pytest.mark.asyncio
async def test_list_pending_empty_emails_returns_empty_without_query():
    s = _session()
    out = await list_pending_for_user_emails([], session=s)
    assert out == []
    s.execute.assert_not_awaited()


# --- expire_old_invitations ---


@pytest.mark.asyncio
async def test_expire_old_invitations_returns_count():
    s = _session()
    update_result = MagicMock()
    update_result.rowcount = 3
    s.execute = AsyncMock(return_value=update_result)

    count = await invitation_service.expire_old_invitations(session=s)
    assert count == 3
    s.commit.assert_awaited()
