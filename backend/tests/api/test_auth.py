"""Tests for Authentication, Token Issuance, and Idle Session Expiration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth_service

client = TestClient(app)


class TestAuthAndIdleHandling:
    def test_login_success_returns_bearer_token(self):
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "geosentinel-admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["username"] == "admin"
        assert data["idle_timeout_seconds"] > 0

    def test_login_invalid_password_returns_401(self):
        resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrong-password",
        })
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.json()["detail"]

    def test_authenticated_me_endpoint_with_valid_token(self):
        login_resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "geosentinel-admin",
        })
        token = login_resp.json()["access_token"]

        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "authenticated"
        assert resp.json()["user"]["username"] == "admin"

    def test_missing_or_malformed_token_returns_401(self):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_garbage_token"})
        assert resp.status_code == 401

    def test_idle_timeout_expires_session(self):
        """Simulate idle inactivity exceeding IDLE_TIMEOUT_SECONDS."""
        login_resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "geosentinel-admin",
        })
        token = login_resp.json()["access_token"]

        # First request immediately is active
        r1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200

        # Simulate user going idle: fast-forward last_activity_at by 20 minutes
        with auth_service._SESSIONS_LOCK:
            session = auth_service._ACTIVE_SESSIONS[token]
            session["last_activity_at"] = datetime.now(timezone.utc) - timedelta(minutes=20)

        # Subsequent request must be rejected due to idle timeout
        r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 401
        assert "idle inactivity" in r2.json()["detail"].lower()

    def test_logout_revokes_token_immediately(self):
        login_resp = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "geosentinel-admin",
        })
        token = login_resp.json()["access_token"]

        # Logout
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_resp.status_code == 200
        assert logout_resp.json()["status"] == "logged_out"

        # Subsequent request with revoked token fails
        after_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert after_resp.status_code == 401
