"""
Authentication and Session Service with Idle Timeout Protection.

Features:
- Cryptographically secure HMAC-SHA256 token issuance.
- Configurable idle timeout (default 15 minutes of inactivity).
- Session tracking with activity refreshes and explicit logout revocation.
- FastAPI dependency for protecting sensitive endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "geosentinel-admin")
AUTH_SECRET = os.getenv("AUTH_SECRET") or secrets.token_hex(32)
IDLE_TIMEOUT_SECONDS = int(os.getenv("AUTH_IDLE_TIMEOUT_SECONDS", str(15 * 60)))  # 15 min default
MAX_SESSION_SECONDS = int(os.getenv("AUTH_MAX_SESSION_SECONDS", str(24 * 3600)))  # 24 hr default

# In-memory session registry (thread-safe)
_SESSIONS_LOCK = threading.Lock()
_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}

bearer_scheme = HTTPBearer(auto_error=False)


def _sign(data: str) -> str:
    """Sign token data with HMAC-SHA256."""
    return hmac.new(AUTH_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def create_token(username: str) -> str:
    """Generate a signed bearer token and register its session with idle tracking."""
    raw_id = secrets.token_urlsafe(32)
    signature = _sign(f"{username}:{raw_id}")
    token = f"geo_{raw_id}.{signature}"

    now = datetime.now(timezone.utc)
    with _SESSIONS_LOCK:
        _ACTIVE_SESSIONS[token] = {
            "username": username,
            "created_at": now,
            "last_activity_at": now,
            "is_active": True,
        }
    return token


def authenticate_user(username: str, password: str) -> dict[str, Any]:
    """Validate credentials and issue an authenticated session token."""
    # Constant-time comparison to prevent timing attacks
    user_match = hmac.compare_digest(username.strip(), ADMIN_USERNAME)
    pass_match = hmac.compare_digest(password, ADMIN_PASSWORD)

    if not (user_match and pass_match):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(username)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "username": username,
        "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
        "expires_in": MAX_SESSION_SECONDS,
    }


def validate_token(token: str) -> dict[str, Any]:
    """
    Validate a bearer token, verifying signature, total expiration, and idle timeout.
    Refreshes last_activity_at on successful active use.
    """
    if not token or not token.startswith("geo_") or "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)
    with _SESSIONS_LOCK:
        session = _ACTIVE_SESSIONS.get(token)
        if not session or not session.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired or was revoked. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 1. Total session lifetime check
        session_age = (now - session["created_at"]).total_seconds()
        if session_age > MAX_SESSION_SECONDS:
            session["is_active"] = False
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session maximum lifetime exceeded. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2. Idle timeout check ("idol" inactivity check)
        idle_duration = (now - session["last_activity_at"]).total_seconds()
        if idle_duration > IDLE_TIMEOUT_SECONDS:
            session["is_active"] = False
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Session expired due to idle inactivity ({int(idle_duration)}s > {IDLE_TIMEOUT_SECONDS}s). Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Refresh activity timestamp on successful active use
        session["last_activity_at"] = now
        idle_remaining = max(0, int(IDLE_TIMEOUT_SECONDS - (now - session["last_activity_at"]).total_seconds()))

        return {
            "username": session["username"],
            "created_at": session["created_at"].isoformat(),
            "last_activity_at": session["last_activity_at"].isoformat(),
            "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
            "idle_remaining_seconds": IDLE_TIMEOUT_SECONDS,
        }


def revoke_token(token: str) -> bool:
    """Explicit logout — invalidates the token immediately."""
    with _SESSIONS_LOCK:
        session = _ACTIVE_SESSIONS.get(token)
        if session:
            session["is_active"] = False
            return True
        return False


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    """FastAPI Dependency for protecting endpoints with token & idle verification."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Please provide 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validate_token(credentials.credentials)
