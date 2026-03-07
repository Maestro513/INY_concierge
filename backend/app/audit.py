"""
HIPAA audit logging — tracks who accessed what PHI, when.

Every access to Protected Health Information (PHI) is logged with:
  - timestamp
  - actor (phone number or "system")
  - action (read, create, update, delete)
  - resource type (member_data, reminder, usage, drug_lookup, etc.)
  - resource_id (specific record if applicable)
  - ip_address (of the requester)

Audit logs are append-only and stored in a separate SQLite DB.
In production, these should also be shipped to a SIEM/log aggregator.
"""

import hashlib
import hmac
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

log = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
DEFAULT_AUDIT_DB = os.path.join(_PARENT_DIR, "audit.db")


def _audit_hmac_key() -> bytes:
    """Return HMAC key for audit actor hashing; falls back to a static key."""
    return os.environ.get("AUDIT_HMAC_KEY", "audit-actor-default-key").encode()


def hash_actor(phone: str) -> str:
    """Produce a deterministic, unique pseudonym for an actor.

    Uses HMAC-SHA256 keyed hash so:
    - The same phone always produces the same actor ID (searchable).
    - The phone cannot be reversed without the key.
    - Last-4 appended for human convenience (not relied upon for uniqueness).
    """
    if not phone or len(phone) < 4:
        return "unknown"
    digest = hmac.new(_audit_hmac_key(), phone.encode(), hashlib.sha256).hexdigest()[:16]
    return f"actor:{digest}:{phone[-4:]}"


def mask_phone(phone: str) -> str:
    """Mask phone number: 5551234567 → ***-***-4567"""
    if not phone or len(phone) < 4:
        return "***"
    return f"***-***-{phone[-4:]}"


def mask_medicare(medicare: str) -> str:
    """Mask Medicare number: 1EG4-TE5-MK72 → ****-***-MK72"""
    if not medicare or len(medicare) < 4:
        return "****"
    return f"****-***-{medicare[-4:]}"


def mask_pii_in_string(text: str) -> str:
    """Scrub phone numbers and Medicare-like IDs from a log string."""
    if not text:
        return text
    # 10-digit phone numbers
    text = re.sub(r'\b(\d{3})(\d{3})(\d{4})\b', r'***-***-\3', text)
    # Medicare number patterns (e.g. 1EG4-TE5-MK72)
    text = re.sub(r'\b([A-Z0-9]{4})-([A-Z0-9]{3})-([A-Z0-9]{4})\b', r'****-***-\3', text)
    return text


class AuditLog:
    """Append-only audit trail for PHI access."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("AUDIT_DB_PATH", DEFAULT_AUDIT_DB)
        self._local = threading.local()
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _ensure_table(self):
        conn = self._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                actor       TEXT NOT NULL,
                action      TEXT NOT NULL,
                resource    TEXT NOT NULL,
                resource_id TEXT DEFAULT '',
                ip_address  TEXT DEFAULT '',
                detail      TEXT DEFAULT '',
                created_at  REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_actor
                ON audit_log(actor)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp)
        """)
        conn.commit()

    def record(self, actor: str, action: str, resource: str,
               resource_id: str = "", ip_address: str = "", detail: str = ""):
        """Record an audit event."""
        now = time.time()
        ts = datetime.utcfromtimestamp(now).isoformat() + "Z"
        masked_actor = hash_actor(actor) if actor and actor.isdigit() else actor

        conn = self._conn()
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, actor, action, resource, resource_id, ip_address, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, masked_actor, action, resource, resource_id, ip_address, detail, now),
        )
        conn.commit()

    def query(self, actor: str = None, resource: str = None,
              since: str = None, limit: int = 100) -> list[dict]:
        """Query audit logs (for admin/compliance review)."""
        conn = self._conn()
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if actor:
            sql += " AND actor = ?"
            params.append(hash_actor(actor) if actor.isdigit() else actor)
        if resource:
            sql += " AND resource = ?"
            params.append(resource)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# Singleton
_audit = None


def get_audit_log() -> AuditLog:
    global _audit
    if _audit is None:
        _audit = AuditLog()
        log.info(f"Audit log initialized at {_audit.db_path}")
    return _audit
