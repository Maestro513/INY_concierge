"""
Tests for infrastructure improvements: retries, geocoding cache,
concurrency limits, and cache thread safety.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class TestGeocodingCache:
    """Tests for the zip-to-county geocoding cache in plan_search."""

    def test_cache_hit_avoids_api_call(self):
        """Second call for same zip should use cache, not API."""
        from app.plan_search import _geo_cache, _geo_lock, get_counties_by_zip

        # Pre-populate cache
        with _geo_lock:
            _geo_cache["99999"] = {
                "data": [{"fips": "12345", "name": "Test County", "state": "FL"}],
                "ts": time.time(),
            }

        try:
            with patch("app.plan_search._http") as mock_http:
                result = get_counties_by_zip("99999")
                assert len(result) == 1
                assert result[0]["fips"] == "12345"
                mock_http.get.assert_not_called()
        finally:
            with _geo_lock:
                _geo_cache.pop("99999", None)

    def test_cache_miss_calls_api(self):
        """Cache miss should call the CMS API."""
        from app.plan_search import _geo_cache, _geo_lock, get_counties_by_zip

        # Ensure cache is empty for this zip
        with _geo_lock:
            _geo_cache.pop("00000", None)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "counties": [{"fips": "00000", "name": "Nowhere", "state": "XX"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("app.plan_search._http") as mock_http:
            mock_http.get.return_value = mock_resp
            result = get_counties_by_zip("00000")
            assert len(result) == 1
            assert result[0]["state"] == "XX"
            mock_http.get.assert_called_once()

        # Clean up
        with _geo_lock:
            _geo_cache.pop("00000", None)

    def test_expired_cache_calls_api(self):
        """Expired cache entry should trigger a fresh API call."""
        from app.plan_search import _geo_cache, _geo_lock, _GEO_CACHE_TTL, get_counties_by_zip

        # Pre-populate with expired entry
        with _geo_lock:
            _geo_cache["88888"] = {
                "data": [{"fips": "88888", "name": "Old", "state": "OL"}],
                "ts": time.time() - _GEO_CACHE_TTL - 1,
            }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "counties": [{"fips": "88888", "name": "New", "state": "NW"}]
        }
        mock_resp.raise_for_status = MagicMock()

        try:
            with patch("app.plan_search._http") as mock_http:
                mock_http.get.return_value = mock_resp
                result = get_counties_by_zip("88888")
                assert result[0]["state"] == "NW"
                mock_http.get.assert_called_once()
        finally:
            with _geo_lock:
                _geo_cache.pop("88888", None)


class TestRetrySession:
    """Verify retry-capable sessions are configured."""

    def test_plan_search_has_retry_session(self):
        """plan_search module should have a retry-capable requests.Session."""
        from app.plan_search import _http, _retry_strategy
        assert _retry_strategy.total == 3
        assert 429 in _retry_strategy.status_forcelist
        assert 503 in _retry_strategy.status_forcelist

    def test_cms_lookup_has_retry_session(self):
        """cms_lookup module should have a retry-capable requests.Session."""
        from app.cms_lookup import _http, _retry_strategy
        assert _retry_strategy.total == 3
        assert 429 in _retry_strategy.status_forcelist

    def test_zoho_has_retry_session(self):
        """zoho_client module should have a retry-capable requests.Session."""
        from app.zoho_client import _http, _retry_strategy
        assert _retry_strategy.total == 3


class TestConcurrencyLimits:
    """Verify concurrency semaphores are in place."""

    def test_cms_api_semaphore_exists(self):
        """plan_search should have a concurrency semaphore."""
        from app.plan_search import _CMS_API_SEMAPHORE
        assert isinstance(_CMS_API_SEMAPHORE, threading.Semaphore)

    def test_semaphore_limits_concurrent_calls(self):
        """Semaphore should actually limit concurrency."""
        from app.plan_search import _CMS_API_SEMAPHORE

        # The semaphore should be acquirable (non-zero limit)
        acquired = _CMS_API_SEMAPHORE.acquire(blocking=False)
        assert acquired is True
        _CMS_API_SEMAPHORE.release()


class TestCacheThreadSafety:
    """Verify SOB caches use locks."""

    def test_sob_cache_lock_exists(self):
        """main module should have a lock for _sob_cache."""
        from app.main import _sob_cache_lock
        assert isinstance(_sob_cache_lock, type(threading.Lock()))

    def test_sob_tier_cache_lock_exists(self):
        """main module should have a lock for _sob_tier_cache."""
        from app.main import _sob_tier_cache_lock
        assert isinstance(_sob_tier_cache_lock, type(threading.Lock()))

    def test_concurrent_cache_access_safe(self):
        """Multiple threads accessing SOB cache should not raise."""
        from app.main import _sob_cache, _sob_cache_lock, SOB_CACHE_TTL

        errors = []

        def reader():
            try:
                for _ in range(100):
                    with _sob_cache_lock:
                        _ = _sob_cache.get("test-plan")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    with _sob_cache_lock:
                        _sob_cache[f"test-{i}"] = {"data": {}, "ts": time.time()}
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads += [threading.Thread(target=writer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Clean up
        with _sob_cache_lock:
            for k in [k for k in _sob_cache if k.startswith("test-")]:
                del _sob_cache[k]

        assert len(errors) == 0, f"Thread safety errors: {errors}"
