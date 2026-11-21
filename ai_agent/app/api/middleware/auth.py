"""API key authentication and security middleware."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.monitoring.logger import get_logger

logger = get_logger("middleware.auth")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Verify incoming X-API-Key matches configured secret."""
    settings = get_settings()

    # In local development or testing with default dummy secret, allow access if not explicitly secured
    if settings.app_env.value in ("development", "testing") and (
        not settings.api_secret_key or settings.api_secret_key == "CHANGE_ME_TO_A_RANDOM_SECRET_KEY"
    ):
        return api_key or "dev_default_key"

    if not api_key:
        logger.warning("Request rejected: missing X-API-Key header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required 'X-API-Key' authentication header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.api_secret_key:
        logger.warning("Request rejected: invalid API key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key
