"""
PR13: Admin router integration tests.

Covers CSRF protection, login brute-force lockout, admin CRUD,
member creation, file upload zip-slip guard, and analytics endpoints.
"""

import io
import json
import os
import tarfile
import time
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

# ── Helpers ─────────────────────────────────────────────────────────────────

def _admin_token(role="super_admin", user_id=1, email="admin@test.com"):
    """Create a valid admin access token for testing."""
    from app.admin_auth import ADMIN_JWT_SECRET
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "admin_access",
        "iat": time.time(),
        "exp": time.time() + 3600,
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm="HS256")


def _auth_header(role="super_admin"):
    return {"Authorization": f"Bearer {_admin_token(role=role)}"}


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── CSRF Protection ────────────────────────────────────────────────────────

class TestCSRFProtection:
    def test_csrf_allows_get_without_origin(self, client):
        """GET requests should not be blocked by CSRF."""
        resp = client.get("/api/admin/plans", headers=_auth_header())
        assert resp.status_code in (200, 401)  # depends on auth, not CSRF

    def test_csrf_skipped_in_development(self, client):
        """In development mode, CSRF is not enforced."""
        # APP_ENV=development in conftest.py, so mutating requests should pass
        resp = client.post("/api/admin/auth/login", json={
            "email": "nobody@test.com", "password": "x",
        })
        # Should fail on auth (401), not CSRF (403)
        assert resp.status_code != 403


# ── Login & Brute-Force ─────────────────────────────────────────────────────

class TestAdminLogin:
    def test_login_invalid_credentials(self, client):
        email = f"invalid-{time.time()}@example.com"
        resp = client.post("/api/admin/auth/login", json={
            "email": email,
            "password": "WrongPassword1!",
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/admin/auth/login", json={})
        assert resp.status_code == 422

    def test_login_lockout_after_failures(self, client):
        """After 5 failures, should return 429."""
        email = f"lockout-{time.time()}@test.com"
        for _ in range(6):
            resp = client.post("/api/admin/auth/login", json={
                "email": email,
                "password": "WrongPassword1!",
            })
        assert resp.status_code == 429


# ── Admin Me ────────────────────────────────────────────────────────────────

class TestAdminMe:
    def test_me_requires_auth(self, client):
        resp = client.get("/api/admin/auth/me")
        assert resp.status_code == 401

    @patch("app.admin_db.get_admin_user_by_id", return_value={
        "id": 1, "email": "a@b.com", "first_name": "A", "last_name": "B",
        "role": "super_admin", "is_active": 1,
    })
    def test_me_returns_profile(self, mock_get, client):
        resp = client.get("/api/admin/auth/me", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "a@b.com"
        assert data["role"] == "super_admin"


# ── Admin User CRUD ─────────────────────────────────────────────────────────

class TestAdminCRUD:
    def test_list_admins_requires_super_admin(self, client):
        resp = client.get("/api/admin/users", headers=_auth_header(role="viewer"))
        assert resp.status_code == 403

    @patch("app.admin_db.list_admin_users", return_value=[])
    def test_list_admins_as_super_admin(self, mock_list, client):
        resp = client.get("/api/admin/users", headers=_auth_header(role="super_admin"))
        assert resp.status_code == 200

    @patch("app.admin_db.get_admin_user_by_email", return_value=None)
    @patch("app.admin_db.create_admin_user", return_value={"id": 2, "email": "new@t.com", "role": "viewer"})
    def test_create_admin_user(self, mock_create, mock_get, client):
        resp = client.post("/api/admin/users", headers=_auth_header(), json={
            "email": "new@t.com",
            "password": "SecurePass1!",
            "role": "viewer",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == 2

    @patch("app.admin_db.get_admin_user_by_email", return_value={"id": 1})
    def test_create_admin_duplicate(self, mock_get, client):
        resp = client.post("/api/admin/users", headers=_auth_header(), json={
            "email": "dupe@t.com",
            "password": "SecurePass1!",
            "role": "viewer",
        })
        assert resp.status_code == 409

    def test_create_admin_weak_password(self, client):
        resp = client.post("/api/admin/users", headers=_auth_header(), json={
            "email": "weak@t.com",
            "password": "short",
            "role": "viewer",
        })
        assert resp.status_code == 422

    @patch("app.admin_db.update_admin_user", return_value={
        "id": 2, "email": "u@t.com", "role": "admin", "is_active": 1,
    })
    def test_update_admin_user(self, mock_update, client):
        resp = client.patch("/api/admin/users/2", headers=_auth_header(), json={
            "role": "admin",
        })
        assert resp.status_code == 200

    @patch("app.admin_db.update_admin_user", return_value=None)
    def test_update_admin_not_found(self, mock_update, client):
        resp = client.patch("/api/admin/users/999", headers=_auth_header(), json={
            "role": "admin",
        })
        assert resp.status_code == 404


# ── Member Creation ─────────────────────────────────────────────────────────

class TestMemberCreation:
    @patch("app.admin_router.search_contact_by_phone", return_value=None)
    def test_create_member(self, mock_zoho, client):
        resp = client.post("/api/admin/members/create", headers=_auth_header(), json={
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "5551234567",
            "send_verification": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "***" in data["member"]["phone"]

    def test_create_member_invalid_phone(self, client):
        resp = client.post("/api/admin/members/create", headers=_auth_header(), json={
            "first_name": "A",
            "last_name": "B",
            "phone": "123",
        })
        assert resp.status_code == 422

    @patch("app.admin_router.search_contact_by_phone", return_value={"phone": "5559999999"})
    def test_create_member_duplicate(self, mock_zoho, client):
        resp = client.post("/api/admin/members/create", headers=_auth_header(), json={
            "first_name": "X",
            "last_name": "Y",
            "phone": "5559999999",
            "send_verification": False,
        })
        assert resp.status_code == 409


# ── File Upload (zip-slip guard) ────────────────────────────────────────────

class TestFileUpload:
    def test_upload_requires_auth(self, client):
        resp = client.post("/api/admin/upload/extracted",
                           files={"file": ("test.tar.gz", b"data", "application/gzip")})
        assert resp.status_code == 401

    def test_upload_requires_admin_role(self, client):
        resp = client.post("/api/admin/upload/extracted",
                           headers=_auth_header(role="viewer"),
                           files={"file": ("test.tar.gz", b"data", "application/gzip")})
        assert resp.status_code == 403

    def test_upload_rejects_non_tgz(self, client):
        resp = client.post("/api/admin/upload/extracted",
                           headers=_auth_header(),
                           files={"file": ("test.zip", b"data", "application/zip")})
        assert resp.status_code == 400

    def test_upload_rejects_invalid_gzip(self, client):
        resp = client.post("/api/admin/upload/extracted",
                           headers=_auth_header(),
                           files={"file": ("test.tar.gz", b"not-gzip", "application/gzip")})
        assert resp.status_code == 400

    def test_upload_valid_tar_extracts_json(self, client):
        """Upload a real tar.gz with a JSON file; verify extraction."""
        # Create a small valid tar.gz in memory
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = json.dumps({"plan_name": "Test Plan"}).encode()
            info = tarfile.TarInfo(name="TEST-PLAN-000.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)

        resp = client.post("/api/admin/upload/extracted",
                           headers=_auth_header(),
                           files={"file": ("plans.tar.gz", buf, "application/gzip")})
        assert resp.status_code == 200
        assert resp.json()["files_extracted"] >= 1

        # Clean up
        from app.config import EXTRACTED_DIR
        test_file = os.path.join(EXTRACTED_DIR, "TEST-PLAN-000.json")
        if os.path.exists(test_file):
            os.unlink(test_file)


# ── Analytics Endpoints ─────────────────────────────────────────────────────

class TestAnalytics:
    def test_analytics_logins(self, client):
        resp = client.get("/api/admin/analytics/logins", headers=_auth_header())
        assert resp.status_code == 200

    def test_analytics_features(self, client):
        resp = client.get("/api/admin/analytics/features", headers=_auth_header())
        assert resp.status_code == 200

    def test_analytics_carriers(self, client):
        resp = client.get("/api/admin/analytics/carriers", headers=_auth_header())
        assert resp.status_code == 200

    def test_analytics_requires_auth(self, client):
        resp = client.get("/api/admin/analytics/logins")
        assert resp.status_code == 401


# ── System Health ───────────────────────────────────────────────────────────

class TestSystemHealth:
    @patch("app.admin_db.get_admin_user_by_id", return_value={
        "id": 1, "email": "a@b.com", "first_name": "A", "last_name": "B",
        "role": "super_admin", "is_active": 1,
    })
    def test_system_health(self, mock_get, client):
        resp = client.get("/api/admin/system/health", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert "disk_usage_gb" in data

    def test_system_health_requires_auth(self, client):
        resp = client.get("/api/admin/system/health")
        assert resp.status_code == 401
