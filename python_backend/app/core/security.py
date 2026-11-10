"""API authentication between the Flutter app and the backend."""

import secrets

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(
    scheme_name="Bearer Authentication",
    description="Enter your JARVIS API token."
)


def verify_token(
    credentials: HTTPAuthorizationCredentials = __import__(
        "fastapi"
    ).Depends(bearer_scheme)
) -> None:

    supplied = credentials.credentials.strip()

    if not secrets.compare_digest(supplied, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token."
        )