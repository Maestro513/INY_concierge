"""
Lightweight circuit breaker for downstream service calls.

Tracks consecutive failures per named service. When failures exceed
`failure_threshold`, the breaker opens and immediately raises
`CircuitOpenError` for `recovery_timeout` seconds without calling the
downstream service.  After the timeout, a single probe request is allowed;
if it succeeds the breaker resets, otherwise it re-opens.

Usage:
    breaker = CircuitBreaker("zoho", failure_threshold=5, recovery_timeout=30)
    with breaker:
        resp = requests.get("https://api.zoho.com/...")
"""

import logging
import threading
import time

log = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are not allowed."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker '{name}' is open. Retry after {retry_after:.0f}s")


class CircuitBreaker:
    """Thread-safe circuit breaker with three states: closed, open, half-open."""

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._lock = threading.Lock()
        self._failure_count = 0
        self._opened_at: float = 0
        self._state = "closed"  # closed | open | half_open

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open":
                if time.time() - self._opened_at >= self.recovery_timeout:
                    self._state = "half_open"
            return self._state

    def _record_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state != "closed":
                log.info("Circuit breaker '%s' closed (service recovered)", self.name)
            self._state = "closed"

    def _record_failure(self):
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.time()
                log.warning(
                    "Circuit breaker '%s' opened after %d failures",
                    self.name,
                    self._failure_count,
                )

    def __enter__(self):
        with self._lock:
            if self._state == "open":
                if time.time() - self._opened_at >= self.recovery_timeout:
                    self._state = "half_open"
                else:
                    retry_after = self.recovery_timeout - (time.time() - self._opened_at)
                    raise CircuitOpenError(self.name, max(0, retry_after))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._record_success()
        elif exc_type is not CircuitOpenError:
            self._record_failure()
        return False  # don't suppress exceptions


# Pre-configured breakers for each downstream service
zoho_breaker = CircuitBreaker("zoho", failure_threshold=3, recovery_timeout=30)
anthropic_breaker = CircuitBreaker("anthropic", failure_threshold=3, recovery_timeout=60)
cms_breaker = CircuitBreaker("cms_marketplace", failure_threshold=5, recovery_timeout=30)
google_breaker = CircuitBreaker("google_geocoding", failure_threshold=5, recovery_timeout=30)
aetna_breaker = CircuitBreaker("aetna", failure_threshold=3, recovery_timeout=30)
uhc_breaker = CircuitBreaker("uhc", failure_threshold=3, recovery_timeout=30)
