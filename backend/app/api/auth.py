"""Authentication API router — login, token issuance, idle verification, and logout."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    username: str
    idle_timeout_seconds: int
    expires_in: int


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> dict[str, Any]:
    """Authenticate and obtain an access token with idle session tracking."""
    return auth_service.authenticate_user(req.username, req.password)


@router.get("/me")
def get_current_user_profile(
    user: dict[str, Any] = Depends(auth_service.get_current_user),
) -> dict[str, Any]:
    """Verify the active token and return remaining idle time before timeout."""
    return {"status": "authenticated", "user": user}


@router.post("/logout")
def logout(
    user: dict[str, Any] = Depends(auth_service.get_current_user),
    credentials=Depends(auth_service.bearer_scheme),
) -> dict[str, Any]:
    """Revoke the current access token."""
    if credentials and credentials.credentials:
        auth_service.revoke_token(credentials.credentials)
    return {"status": "logged_out", "message": "Token has been revoked."}


@router.get("/status")
def auth_status() -> dict[str, Any]:
    """Report authentication settings and idle session timeout configuration."""
    return {
        "auth_enabled": True,
        "idle_timeout_seconds": auth_service.IDLE_TIMEOUT_SECONDS,
        "max_session_seconds": auth_service.MAX_SESSION_SECONDS,
    }
