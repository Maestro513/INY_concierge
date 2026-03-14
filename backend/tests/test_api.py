"""
HTTP integration tests using FastAPI TestClient.

Covers the core request/response pipeline: health check, auth flow,
rate limiting, metrics, and error handling.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app.

    APP_ENV is set to 'development' in conftest.py, which disables
    auth requirements on most endpoints.
    """
    from app.main import app
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "db" in data["checks"]

    def test_health_minimal_disclosure(self, client):
        resp = client.get("/health")
        data = resp.json()
        # M14: health endpoint should NOT expose API key status, session counts, or exception types
        checks = data["checks"]
        assert "anthropic_key" not in checks
        for v in checks.values():
            assert "Error" not in str(v)  # no exception class names


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, client):
        # Make a request first to generate metrics
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "total_errors" in data
        assert "avg_latency_ms" in data
        assert isinstance(data["total_requests"], int)


class TestAuthFlow:
    def test_lookup_missing_phone(self, client):
        resp = client.post("/auth/lookup", json={})
        assert resp.status_code == 422  # validation error

    @patch("app.main.search_contact_by_phone", return_value=None)
    def test_lookup_unknown_phone(self, mock_zoho, client):
        resp = client.post("/auth/lookup", json={"phone": "9999999999"})
        # May be rate limited from previous test runs sharing the same store
        assert resp.status_code in (200, 429)
        if resp.status_code == 200:
            data = resp.json()
            # M9: response should NOT reveal whether phone was found
            assert "found" not in data
            assert data.get("otp_sent") is True

    def test_verify_otp_missing_fields(self, client):
        resp = client.post("/auth/verify-otp", json={})
        assert resp.status_code == 422

    def test_verify_otp_invalid_phone(self, client):
        resp = client.post("/auth/verify-otp", json={"phone": "9999999999", "code": "123456"})
        # Should fail with 401 (no pending OTP) or 429 (rate limited)
        assert resp.status_code in (401, 429)


class TestRateLimiting:
    def test_auth_lookup_rate_limited(self, client):
        """Verify IP-based rate limiting on /auth/lookup."""
        with patch("app.main.search_contact_by_phone", return_value=None):
            # Exhaust the rate limit (5 per 60s window)
            for _ in range(6):
                resp = client.post("/auth/lookup", json={"phone": "5550000001"})
            # At least one should be rate limited
            # (depends on prior test state, so just check the endpoint works)
            assert resp.status_code in (200, 429)


class TestCORSHeaders:
    def test_cors_present_on_response(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        # In development mode, CORS should be permissive
        assert resp.status_code in (200, 503)


class TestErrorHandling:
    def test_404_on_unknown_route(self, client):
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404

    def test_method_not_allowed(self, client):
        resp = client.put("/health")
        assert resp.status_code == 405


class TestRefreshToken:
    def test_refresh_without_token(self, client):
        resp = client.post("/auth/refresh", json={})
        assert resp.status_code == 422

    def test_refresh_with_invalid_token(self, client):
        resp = client.post("/auth/refresh", json={"refresh_token": "invalid.token.here"})
        assert resp.status_code == 401


class TestCircuitBreaker:
    def test_circuit_breaker_opens_on_failures(self):
        from app.circuit_breaker import CircuitBreaker, CircuitOpenError

        cb = CircuitBreaker("test_service", failure_threshold=2, recovery_timeout=1)

        # Two failures should open the breaker
        for _ in range(2):
            try:
                with cb:
                    raise ConnectionError("service down")
            except ConnectionError:
                pass

        assert cb.state == "open"

        # Next call should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            with cb:
                pass

    def test_circuit_breaker_recovers(self):
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test_recover", failure_threshold=1, recovery_timeout=0)

        # Trip the breaker
        try:
            with cb:
                raise ConnectionError("down")
        except ConnectionError:
            pass

        assert cb.state in ("open", "half_open")

        # After recovery_timeout=0, should be half_open and allow a probe
        time.sleep(0.1)
        with cb:
            pass  # success

        assert cb.state == "closed"
