"""
Caregiver / Family Access module.

Manages the invite → accept → read-only-mirror flow for caregivers.

Tables (in persistent_store.db):
  caregiver_invites  — pending/accepted/revoked invites
  caregiver_consent  — HIPAA authorization records (append-only audit)

Flow:
  1. Member views HIPAA consent → approves → enters caregiver phone → invite created
  2. SMS sent to caregiver with invite code (48h expiry)
  3. Caregiver downloads app → verifies phone → sees invite prompt
  4. Caregiver accepts → status = accepted → read-only mirror access
  5. Member can revoke anytime from Settings
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
from datetime import datetime
from typing import Optional

from .encryption import get_cipher

log = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
_PERSISTENT_DIR = "/data" if os.path.isdir("/data") else _PARENT_DIR
DEFAULT_CAREGIVER_DB = os.path.join(_PERSISTENT_DIR, "caregiver.db")

# Invite code validity (48 hours)
INVITE_TTL = 48 * 60 * 60

# Max caregivers per member
MAX_CAREGIVERS_PER_MEMBER = 3

# Max pending invites per member (prevents spam)
MAX_PENDING_INVITES = 5


class CaregiverDB:
    """CRUD for caregiver invites, consent records, and access links."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("CAREGIVER_DB_PATH", DEFAULT_CAREGIVER_DB)
        self._local = threading.local()
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.OperationalError:
                pass
            self._local.conn = conn
        return conn

    def _ensure_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS caregiver_invites (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                member_phone    TEXT NOT NULL,
                caregiver_phone TEXT NOT NULL,
                invite_code     TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      REAL NOT NULL,
                expires_at      REAL NOT NULL,
                accepted_at     REAL,
                revoked_at      REAL,
                revoked_by      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cg_member
                ON caregiver_invites(member_phone, status);
            CREATE INDEX IF NOT EXISTS idx_cg_caregiver
                ON caregiver_invites(caregiver_phone, status);
            CREATE INDEX IF NOT EXISTS idx_cg_code
                ON caregiver_invites(invite_code);

            CREATE TABLE IF NOT EXISTS caregiver_consent (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                member_phone    TEXT NOT NULL,
                caregiver_phone TEXT,
                consent_type    TEXT NOT NULL,
                consent_text    TEXT NOT NULL,
                consented_at    REAL NOT NULL,
                ip_address      TEXT DEFAULT '',
                device_info     TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_consent_member
                ON caregiver_consent(member_phone);

            CREATE TABLE IF NOT EXISTS caregiver_access_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                caregiver_phone TEXT NOT NULL,
                member_phone    TEXT NOT NULL,
                action          TEXT NOT NULL,
                resource        TEXT DEFAULT '',
                accessed_at     REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_access_log
                ON caregiver_access_log(caregiver_phone, accessed_at);
        """)
        conn.commit()

    # ── Phone hashing (same key as PersistentStore) ─────────────────────

    @staticmethod
    def _hash_phone(phone: str) -> str:
        key = os.environ.get("FIELD_ENCRYPTION_KEY", "dev-key").encode()
        return hmac.new(key, phone.encode(), hashlib.sha256).hexdigest()

    # ── Consent ─────────────────────────────────────────────────────────

    def record_consent(
        self,
        member_phone: str,
        caregiver_phone: Optional[str],
        consent_type: str,
        consent_text: str,
        ip_address: str = "",
        device_info: str = "",
    ) -> int:
        """Record a HIPAA consent/authorization event. Append-only."""
        conn = self._conn()
        cursor = conn.execute(
            """INSERT INTO caregiver_consent
               (member_phone, caregiver_phone, consent_type, consent_text, consented_at, ip_address, device_info)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                self._hash_phone(member_phone),
                self._hash_phone(caregiver_phone) if caregiver_phone else None,
                consent_type,
                consent_text,
                time.time(),
                ip_address,
                device_info,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    # ── Invites ─────────────────────────────────────────────────────────

    def create_invite(self, member_phone: str, caregiver_phone: str) -> dict:
        """Create a caregiver invite. Returns invite dict with code.

        Raises ValueError if limits exceeded or duplicate active invite exists.
        """
        conn = self._conn()
        member_hash = self._hash_phone(member_phone)
        caregiver_hash = self._hash_phone(caregiver_phone)
        now = time.time()

        # Check: caregiver can't invite themselves
        if member_phone == caregiver_phone:
            raise ValueError("You cannot invite yourself as a caregiver.")

        # Check: already has an active (accepted) link
        existing = conn.execute(
            "SELECT id FROM caregiver_invites WHERE member_phone = ? AND caregiver_phone = ? AND status = 'accepted'",
            (member_hash, caregiver_hash),
        ).fetchone()
        if existing:
            raise ValueError("This person already has access to your plan.")

        # Check: already has a pending invite
        pending = conn.execute(
            "SELECT id FROM caregiver_invites WHERE member_phone = ? AND caregiver_phone = ? AND status = 'pending' AND expires_at > ?",
            (member_hash, caregiver_hash, now),
        ).fetchone()
        if pending:
            raise ValueError("An invite is already pending for this phone number.")

        # Check: max active caregivers
        active_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM caregiver_invites WHERE member_phone = ? AND status = 'accepted'",
            (member_hash,),
        ).fetchone()["cnt"]
        if active_count >= MAX_CAREGIVERS_PER_MEMBER:
            raise ValueError(f"You can have up to {MAX_CAREGIVERS_PER_MEMBER} caregivers.")

        # Check: max pending invites
        pending_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM caregiver_invites WHERE member_phone = ? AND status = 'pending' AND expires_at > ?",
            (member_hash, now),
        ).fetchone()["cnt"]
        if pending_count >= MAX_PENDING_INVITES:
            raise ValueError("Too many pending invites. Please wait for existing invites to expire or revoke them.")

        # Generate 6-digit invite code
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = now + INVITE_TTL

        conn.execute(
            """INSERT INTO caregiver_invites
               (member_phone, caregiver_phone, invite_code, status, created_at, expires_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (member_hash, caregiver_hash, code, now, expires_at),
        )
        conn.commit()

        return {
            "invite_code": code,
            "expires_at": expires_at,
            "caregiver_phone": caregiver_phone,
        }

    def check_pending_invite(self, caregiver_phone: str) -> Optional[dict]:
        """Check if a phone number has any pending (non-expired) invites.

        Returns the invite details if found, None otherwise.
        Used at login time to route caregiver to the accept flow.
        """
        conn = self._conn()
        caregiver_hash = self._hash_phone(caregiver_phone)
        now = time.time()

        row = conn.execute(
            """SELECT id, member_phone, invite_code, created_at, expires_at
               FROM caregiver_invites
               WHERE caregiver_phone = ? AND status = 'pending' AND expires_at > ?
               ORDER BY created_at DESC LIMIT 1""",
            (caregiver_hash, now),
        ).fetchone()

        if not row:
            return None

        return {
            "invite_id": row["id"],
            "member_phone_hash": row["member_phone"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    def accept_invite(self, caregiver_phone: str, invite_code: str) -> dict:
        """Accept a pending invite by code. Returns member info needed to look up the session.

        Raises ValueError if code invalid/expired.
        """
        conn = self._conn()
        caregiver_hash = self._hash_phone(caregiver_phone)
        now = time.time()

        row = conn.execute(
            """SELECT id, member_phone, expires_at
               FROM caregiver_invites
               WHERE caregiver_phone = ? AND invite_code = ? AND status = 'pending'""",
            (caregiver_hash, invite_code),
        ).fetchone()

        if not row:
            raise ValueError("Invalid or expired invite code.")

        if now > row["expires_at"]:
            conn.execute(
                "UPDATE caregiver_invites SET status = 'expired' WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            raise ValueError("This invite has expired. Please ask the member to send a new one.")

        conn.execute(
            "UPDATE caregiver_invites SET status = 'accepted', accepted_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()

        return {
            "invite_id": row["id"],
            "member_phone_hash": row["member_phone"],
        }

    def get_active_caregivers(self, member_phone: str) -> list[dict]:
        """Get all accepted (active) caregivers for a member."""
        conn = self._conn()
        member_hash = self._hash_phone(member_phone)
        rows = conn.execute(
            """SELECT id, caregiver_phone, accepted_at
               FROM caregiver_invites
               WHERE member_phone = ? AND status = 'accepted'
               ORDER BY accepted_at DESC""",
            (member_hash,),
        ).fetchall()

        return [
            {
                "invite_id": r["id"],
                "caregiver_phone_hash": r["caregiver_phone"],
                "accepted_at": r["accepted_at"],
            }
            for r in rows
        ]

    def get_pending_invites(self, member_phone: str) -> list[dict]:
        """Get all pending (non-expired) invites for a member."""
        conn = self._conn()
        member_hash = self._hash_phone(member_phone)
        now = time.time()
        rows = conn.execute(
            """SELECT id, caregiver_phone, created_at, expires_at
               FROM caregiver_invites
               WHERE member_phone = ? AND status = 'pending' AND expires_at > ?
               ORDER BY created_at DESC""",
            (member_hash, now),
        ).fetchall()

        return [
            {
                "invite_id": r["id"],
                "caregiver_phone_hash": r["caregiver_phone"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
            }
            for r in rows
        ]

    def revoke_access(self, member_phone: str, invite_id: int, revoked_by: str = "member") -> bool:
        """Revoke an accepted or pending invite. Returns True if updated."""
        conn = self._conn()
        member_hash = self._hash_phone(member_phone)
        now = time.time()

        cursor = conn.execute(
            """UPDATE caregiver_invites
               SET status = 'revoked', revoked_at = ?, revoked_by = ?
               WHERE id = ? AND member_phone = ? AND status IN ('accepted', 'pending')""",
            (now, revoked_by, invite_id, member_hash),
        )
        conn.commit()
        return cursor.rowcount > 0

    def is_active_caregiver(self, caregiver_phone: str, member_phone: str) -> bool:
        """Check if caregiver has active (accepted) access to member's data."""
        conn = self._conn()
        row = conn.execute(
            """SELECT id FROM caregiver_invites
               WHERE caregiver_phone = ? AND member_phone = ? AND status = 'accepted'""",
            (self._hash_phone(caregiver_phone), self._hash_phone(member_phone)),
        ).fetchone()
        return row is not None

    def get_members_for_caregiver(self, caregiver_phone: str) -> list[dict]:
        """Get all members this caregiver has active access to.

        Returns list of member_phone_hash values — the caller must
        resolve them to actual member sessions.
        """
        conn = self._conn()
        caregiver_hash = self._hash_phone(caregiver_phone)
        rows = conn.execute(
            """SELECT id, member_phone, accepted_at
               FROM caregiver_invites
               WHERE caregiver_phone = ? AND status = 'accepted'
               ORDER BY accepted_at DESC""",
            (caregiver_hash,),
        ).fetchall()

        return [
            {
                "invite_id": r["id"],
                "member_phone_hash": r["member_phone"],
                "accepted_at": r["accepted_at"],
            }
            for r in rows
        ]

    def log_access(self, caregiver_phone: str, member_phone: str, action: str, resource: str = ""):
        """Log a caregiver's access to member data (HIPAA audit trail)."""
        conn = self._conn()
        conn.execute(
            """INSERT INTO caregiver_access_log
               (caregiver_phone, member_phone, action, resource, accessed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                self._hash_phone(caregiver_phone),
                self._hash_phone(member_phone),
                action,
                resource,
                time.time(),
            ),
        )
        conn.commit()

    def get_access_log(self, member_phone: str, limit: int = 50) -> list[dict]:
        """Get recent access logs for a member (for admin/audit)."""
        conn = self._conn()
        member_hash = self._hash_phone(member_phone)
        rows = conn.execute(
            """SELECT caregiver_phone, action, resource, accessed_at
               FROM caregiver_access_log
               WHERE member_phone = ?
               ORDER BY accessed_at DESC LIMIT ?""",
            (member_hash, limit),
        ).fetchall()

        return [
            {
                "caregiver_phone_hash": r["caregiver_phone"],
                "action": r["action"],
                "resource": r["resource"],
                "accessed_at": r["accessed_at"],
            }
            for r in rows
        ]

    # ── Admin helpers ───────────────────────────────────────────────────

    def admin_get_all_links(self, status: str = None, limit: int = 100) -> list[dict]:
        """Admin: list all caregiver links, optionally filtered by status."""
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM caregiver_invites WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM caregiver_invites ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]

    def admin_revoke(self, invite_id: int) -> bool:
        """Admin: revoke any invite regardless of member."""
        conn = self._conn()
        cursor = conn.execute(
            "UPDATE caregiver_invites SET status = 'revoked', revoked_at = ?, revoked_by = 'admin' WHERE id = ? AND status IN ('accepted', 'pending')",
            (time.time(), invite_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def cleanup_expired(self):
        """Mark expired pending invites."""
        conn = self._conn()
        now = time.time()
        conn.execute(
            "UPDATE caregiver_invites SET status = 'expired' WHERE status = 'pending' AND expires_at < ?",
            (now,),
        )
        conn.commit()
