"""Optional admin auth.

When ``settings.admin_token`` is set, destructive routes require an
``Authorization: Bearer <token>`` header. When unset, the dependency is a no-op
so local development works without ceremony.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    if settings.admin_token is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization[len("Bearer "):].strip()
    if presented != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )
