import uuid

from app.config import settings


def get_tenant_id() -> uuid.UUID:
    """FastAPI dependency — returns the seed tenant ID for now."""
    return uuid.UUID(settings.seed_tenant_id)
