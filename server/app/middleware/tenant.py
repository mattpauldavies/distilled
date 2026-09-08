import uuid

from fastapi import Depends

from app.auth import CurrentUser, require_auth


async def get_tenant_id(current_user: CurrentUser = Depends(require_auth)) -> uuid.UUID:
    """FastAPI dependency — extracts tenant_id from the authenticated user."""
    return current_user.tenant_id
