"""
Persistent OTP + Session store backed by SQLite.

Replaces the in-memory dicts in auth.py and main.py so that
server restarts / deploys don't wipe active OTPs or sessions.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time

from .encryption import get_cipher

log = logging.getLogger(__name__)

# PHI fields within member_data that must be encrypted at rest
_PHI_FIELDS = ("medicare_number", "medications", "phone")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
# Prefer persistent disk mount (/data) on Render; fall back to local dir for dev
_PERSISTENT_DIR = "/data" if os.path.isdir("/data") else _PARENT_DIR
DEFAULT_STORE_DB = os.path.join(_PERSISTENT_DIR, "persistent_store.db")


class PersistentStore:
    """SQLite-backed store for OTP codes and user sessions."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("STORE_DB_PATH", DEFAULT_STORE_DB)
        self._local = threading.local()
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
            self._local.conn = conn
        return conn

    def _ensure_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS otp_store (
                phone           TEXT PRIMARY KEY,
                code_hash       TEXT NOT NULL,
                created_at      REAL NOT NULL,
                ttl             INTEGER NOT NULL DEFAULT 300,
                attempts        INTEGER NOT NULL DEFAULT 0,
                locked_until    REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS otp_send_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                sent_at         REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_otp_send_phone
                ON otp_send_log(phone, sent_at);

            CREATE TABLE IF NOT EXISTS sessions (
                session_id      TEXT PRIMARY KEY,
                phone           TEXT NOT NULL,
                data            TEXT NOT NULL,
                created_at      REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_phone
                ON sessions(phone);

            CREATE TABLE IF NOT EXISTS used_refresh_tokens (
                jti             TEXT PRIMARY KEY,
                phone           TEXT NOT NULL,
                used_at         REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rate_limit_hits (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                key             TEXT NOT NULL,
                hit_at          REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rate_limit_key
                ON rate_limit_hits(key, hit_at);

            CREATE TABLE IF NOT EXISTS worker_metrics (
                worker_id       TEXT PRIMARY KEY,
                total           INTEGER NOT NULL DEFAULT 0,
                errors          INTEGER NOT NULL DEFAULT 0,
                latency_sum     REAL NOT NULL DEFAULT 0.0,
                updated_at      REAL NOT NULL
            );
        """)
        conn.commit()
        log.info(f"Persistent store ready at {self.db_path}")

    # ── OTP Methods ───────────────────────────────────────────────────────

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def generate_otp(self, phone: str, *, otp_ttl: int = 300,
                     max_sends: int = 5, send_window: int = 600) -> str | None:
        now = time.time()
        conn = self._conn()

        # Rate limiting — count recent sends
        cutoff = now - send_window
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM otp_send_log WHERE phone = ? AND sent_at > ?",
            (phone, cutoff),
        ).fetchone()
        if row["cnt"] >= max_sends:
            log.warning(f"OTP rate limit hit for phone ending {phone[-4:]}")
            return None

        # Log this send
        conn.execute("INSERT INTO otp_send_log (phone, sent_at) VALUES (?, ?)", (phone, now))

        # Generate code
        code = f"{secrets.randbelow(900000) + 100000}"

        # Upsert OTP entry
        conn.execute(
            """INSERT INTO otp_store (phone, code_hash, created_at, ttl, attempts, locked_until)
               VALUES (?, ?, ?, ?, 0, 0)
               ON CONFLICT(phone) DO UPDATE SET
                   code_hash = excluded.code_hash,
                   created_at = excluded.created_at,
                   ttl = excluded.ttl,
                   attempts = 0,
                   locked_until = 0""",
            (phone, self._hash_code(code), now, otp_ttl),
        )
        conn.commit()

        # Prune old send log entries (older than window)
        conn.execute("DELETE FROM otp_send_log WHERE sent_at < ?", (cutoff,))
        conn.commit()

        return code

    def verify_otp(self, phone: str, code: str, *,
                   max_attempts: int = 5, lockout_seconds: int = 300) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT * FROM otp_store WHERE phone = ?", (phone,)).fetchone()
        if not row:
            return False

        now = time.time()

        # Check lockout
        if now < row["locked_until"]:
            remaining = int(row["locked_until"] - now)
            log.warning(f"OTP locked for phone ending {phone[-4:]}, {remaining}s remaining")
            return False

        # Check expiration
        if now - row["created_at"] > row["ttl"]:
            conn.execute("DELETE FROM otp_store WHERE phone = ?", (phone,))
            conn.commit()
            return False

        # Check code
        if not hmac.compare_digest(self._hash_code(code), row["code_hash"]):
            attempts = row["attempts"] + 1
            if attempts >= max_attempts:
                conn.execute(
                    "UPDATE otp_store SET attempts = ?, locked_until = ? WHERE phone = ?",
                    (attempts, now + lockout_seconds, phone),
                )
                log.warning(f"OTP locked out for phone ending {phone[-4:]} after {max_attempts} attempts")
            else:
                conn.execute(
                    "UPDATE otp_store SET attempts = ? WHERE phone = ?",
                    (attempts, phone),
                )
            conn.commit()
            return False

        # Success — delete OTP (single-use)
        conn.execute("DELETE FROM otp_store WHERE phone = ?", (phone,))
        conn.commit()
        return True

    def get_otp_send_count(self, phone: str, send_window: int = 600) -> int:
        """Get the number of OTP sends in the current window (for testing)."""
        cutoff = time.time() - send_window
        row = self._conn().execute(
            "SELECT COUNT(*) as cnt FROM otp_send_log WHERE phone = ? AND sent_at > ?",
            (phone, cutoff),
        ).fetchone()
        return row["cnt"]

    # ── Phone Hashing ──────────────────────────────────────────────────────

    @staticmethod
    def _hash_phone(phone: str) -> str:
        """L2: Deterministic hash of phone for indexed lookups (no plaintext storage)."""
        key = os.environ.get("FIELD_ENCRYPTION_KEY", "dev-key").encode()
        return hmac.new(key, phone.encode(), hashlib.sha256).hexdigest()

    # ── PHI Encryption Helpers ────────────────────────────────────────────

    @staticmethod
    def _encrypt_phi(member_data: dict) -> dict:
        """Encrypt PHI fields in member_data before storing.

        Raises RuntimeError if encryption is not configured (prevents
        silent plaintext storage of PHI).
        """
        data = dict(member_data)
        cipher = get_cipher()
        for field in _PHI_FIELDS:
            if field in data and data[field]:
                data[field] = cipher.encrypt(str(data[field]))
        return data

    @staticmethod
    def _decrypt_phi(member_data: dict) -> dict:
        """Decrypt PHI fields in member_data after reading."""
        cipher = get_cipher()
        if not cipher.enabled:
            return member_data
        data = dict(member_data)
        for field in _PHI_FIELDS:
            if field in data and data[field]:
                data[field] = cipher.decrypt(str(data[field]))
        return data

    # ── Session Methods ───────────────────────────────────────────────────

    def create_session(self, phone: str, member_data: dict) -> str:
        sid = secrets.token_urlsafe(32)
        conn = self._conn()
        # L2: Store phone inside encrypted data blob (column stores hash only)
        # Use _session_phone key to avoid collision with PHI_FIELDS "phone" encryption
        data_with_phone = {**member_data, "_session_phone": phone}
        encrypted = self._encrypt_phi(data_with_phone)
        phone_hash = self._hash_phone(phone)
        conn.execute(
            "INSERT INTO sessions (session_id, phone, data, created_at) VALUES (?, ?, ?, ?)",
            (sid, phone_hash, json.dumps(encrypted), time.time()),
        )
        conn.commit()
        self._cleanup_sessions()
        return sid

    def get_session(self, sid: str, ttl: int = 7200) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (sid,)
        ).fetchone()
        if not row:
            return None
        if time.time() - row["created_at"] > ttl:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
            conn.commit()
            return None
        data = self._decrypt_phi(json.loads(row["data"]))
        phone = data.pop("_session_phone", None) or data.get("phone", row["phone"])
        return {
            "phone": phone,
            "data": data,
            "ts": row["created_at"],
        }

    def touch_session(self, sid: str):
        """Extend session TTL by updating created_at."""
        conn = self._conn()
        conn.execute(
            "UPDATE sessions SET created_at = ? WHERE session_id = ?",
            (time.time(), sid),
        )
        conn.commit()

    def delete_sessions_by_phone(self, phone: str) -> int:
        """Delete all sessions for a phone number (logout/revocation)."""
        conn = self._conn()
        phone_hash = self._hash_phone(phone)
        # Support both hashed and legacy plaintext lookups
        cursor = conn.execute("DELETE FROM sessions WHERE phone = ? OR phone = ?", (phone_hash, phone))
        conn.commit()
        return cursor.rowcount

    def find_session_by_phone(self, phone: str, ttl: int = 7200) -> dict | None:
        """Find the most recent session for a phone number."""
        conn = self._conn()
        phone_hash = self._hash_phone(phone)
        # Support both hashed and legacy plaintext lookups
        row = conn.execute(
            "SELECT * FROM sessions WHERE phone = ? OR phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone_hash, phone),
        ).fetchone()
        if not row:
            return None
        if time.time() - row["created_at"] > ttl:
            return None
        data = self._decrypt_phi(json.loads(row["data"]))
        actual_phone = data.pop("_session_phone", None) or data.get("phone", phone)
        return {
            "phone": actual_phone,
            "data": data,
            "ts": row["created_at"],
        }

    def count_active_sessions(self, ttl: int = 7200) -> int:
        cutoff = time.time() - ttl
        row = self._conn().execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE created_at > ?", (cutoff,)
        ).fetchone()
        return row["cnt"]

    def _cleanup_sessions(self, ttl: int = 7200):
        cutoff = time.time() - ttl
        conn = self._conn()
        conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
        conn.commit()

    # ── Cleanup ───────────────────────────────────────────────────────────

    # ── Refresh Token Rotation ────────────────────────────────────────────

    def consume_refresh_jti(self, jti: str, phone: str) -> bool:
        """Mark a refresh token JTI as used. Returns False if already used (replay)."""
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO used_refresh_tokens (jti, phone, used_at) VALUES (?, ?, ?)",
                (jti, phone, time.time()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # JTI already consumed — this is a replay attack
            return False

    # ── Rate Limiting ────────────────────────────────────────────────

    def check_rate_limit(self, key: str, max_hits: int, window: int) -> bool:
        """Check and record a rate limit hit. Returns True if allowed, False if blocked."""
        now = time.time()
        conn = self._conn()
        cutoff = now - window
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM rate_limit_hits WHERE key = ? AND hit_at > ?",
            (key, cutoff),
        ).fetchone()
        if row["cnt"] >= max_hits:
            return False
        conn.execute(
            "INSERT INTO rate_limit_hits (key, hit_at) VALUES (?, ?)",
            (key, now),
        )
        conn.commit()
        return True

    def cleanup_rate_limits(self, max_age: int = 600):
        """Remove old rate limit entries."""
        cutoff = time.time() - max_age
        conn = self._conn()
        conn.execute("DELETE FROM rate_limit_hits WHERE hit_at < ?", (cutoff,))
        conn.commit()

    # ── Worker Metrics (cross-process aggregation) ─────────────────────────

    def upsert_worker_metrics(self, worker_id: str, total: int, errors: int, latency_sum: float) -> None:
        """Upsert this worker's cumulative metrics into the shared table."""
        conn = self._conn()
        conn.execute(
            """INSERT INTO worker_metrics (worker_id, total, errors, latency_sum, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(worker_id) DO UPDATE SET
                 total=excluded.total, errors=excluded.errors,
                 latency_sum=excluded.latency_sum, updated_at=excluded.updated_at""",
            (worker_id, total, errors, latency_sum, time.time()),
        )
        conn.commit()

    def read_aggregate_metrics(self) -> dict:
        """Read summed metrics across all workers (prune stale workers > 5 min)."""
        conn = self._conn()
        cutoff = time.time() - 300  # ignore workers not seen in 5 minutes
        row = conn.execute(
            """SELECT COALESCE(SUM(total),0), COALESCE(SUM(errors),0),
                      COALESCE(SUM(latency_sum),0.0)
               FROM worker_metrics WHERE updated_at > ?""",
            (cutoff,),
        ).fetchone()
        return {"total": row[0], "errors": row[1], "latency_sum": row[2]}

    def cleanup_all(self):
        """Remove all expired entries. Call periodically or on startup."""
        now = time.time()
        conn = self._conn()
        # Expired OTPs (TTL varies, so check each row)
        conn.execute(
            "DELETE FROM otp_store WHERE (created_at + ttl) < ?", (now,)
        )
        # Old send logs (anything > 10 minutes)
        conn.execute("DELETE FROM otp_send_log WHERE sent_at < ?", (now - 600,))
        # Expired sessions
        self._cleanup_sessions()
        # Old used refresh JTIs (older than 30 days)
        conn.execute("DELETE FROM used_refresh_tokens WHERE used_at < ?", (now - 2592000,))
        # Old rate limit entries
        conn.execute("DELETE FROM rate_limit_hits WHERE hit_at < ?", (now - 600,))
        conn.commit()
