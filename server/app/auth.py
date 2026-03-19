import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer_scheme = HTTPBearer()


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not hmac.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
