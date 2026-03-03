"""
Admin portal SQLite database.

Separate from the mobile user data — stores admin accounts,
login events, and search analytics.
"""

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

# Database file lives alongside the mobile SQLite DB
_DB_DIR = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent))
DB_PATH = os.path.join(_DB_DIR, "admin.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT    NOT NULL UNIQUE,
    password_hash TEXT  NOT NULL,
    first_name  TEXT    NOT NULL DEFAULT '',
    last_name   TEXT    NOT NULL DEFAULT '',
    role        TEXT    NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('super_admin', 'admin', 'viewer')),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  REAL    NOT NULL DEFAULT (strftime('%s','now')),
    updated_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS login_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT,
    ip_address  TEXT,
    user_agent  TEXT    DEFAULT '',
    success     INTEGER NOT NULL DEFAULT 0,
    created_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS search_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL DEFAULT 'search',
    query       TEXT    DEFAULT '',
    plan_number TEXT    DEFAULT '',
    phone       TEXT    DEFAULT '',
    metadata    TEXT    DEFAULT '{}',
    created_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
);
"""


def _init_db():
    """Create tables if they don't exist."""
    with _get_conn() as conn:
        conn.executescript(SCHEMA)
    log.info(f"Admin DB initialized at {DB_PATH}")


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Admin Users ──────────────────────────────────────────────────────────────

def create_admin_user(email: str, password_hash: str, first_name: str = "",
                      last_name: str = "", role: str = "viewer") -> dict:
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO admin_users (email, password_hash, first_name, last_name, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (email.lower().strip(), password_hash, first_name, last_name, role),
        )
        # Read back within same connection (before commit)
        row = conn.execute(
            "SELECT * FROM admin_users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row) if row else None


def get_admin_user_by_email(email: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM admin_users WHERE email = ? AND is_active = 1",
            (email.lower().strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_admin_user_by_id(uid: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM admin_users WHERE id = ?", (uid,)
        ).fetchone()
        return dict(row) if row else None


def list_admin_users() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, email, first_name, last_name, role, is_active, created_at "
            "FROM admin_users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_admin_user(uid: int, **fields) -> dict | None:
    allowed = {"email", "first_name", "last_name", "role", "is_active", "password_hash"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_admin_user_by_id(uid)
    updates["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [uid]
    with _get_conn() as conn:
        conn.execute(f"UPDATE admin_users SET {set_clause} WHERE id = ?", values)
    return get_admin_user_by_id(uid)


# ── Login Events ─────────────────────────────────────────────────────────────

def record_login_event(phone: str = "", ip_address: str = "",
                       user_agent: str = "", success: bool = True):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO login_events (phone, ip_address, user_agent, success) "
            "VALUES (?, ?, ?, ?)",
            (phone, ip_address, user_agent, 1 if success else 0),
        )


def get_login_stats(days: int = 30) -> dict:
    cutoff = time.time() - (days * 86400)
    with _get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE created_at > ? AND success = 1",
            (cutoff,),
        ).fetchone()[0]
        unique = conn.execute(
            "SELECT COUNT(DISTINCT phone) FROM login_events WHERE created_at > ? AND success = 1",
            (cutoff,),
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE created_at > ? AND success = 0",
            (cutoff,),
        ).fetchone()[0]
    return {"total_logins": total, "unique_users": unique, "failed_logins": failed, "days": days}


# ── Search Events ────────────────────────────────────────────────────────────

def record_search_event(event_type: str, query: str = "", plan_number: str = "",
                        phone: str = "", metadata: str = "{}"):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO search_events (event_type, query, plan_number, phone, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_type, query, plan_number, phone, metadata),
        )


def get_search_stats(days: int = 30) -> dict:
    cutoff = time.time() - (days * 86400)
    with _get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM search_events WHERE created_at > ?", (cutoff,),
        ).fetchone()[0]
        by_type = conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM search_events "
            "WHERE created_at > ? GROUP BY event_type ORDER BY cnt DESC",
            (cutoff,),
        ).fetchall()
    return {"total": total, "by_type": {r["event_type"]: r["cnt"] for r in by_type}}


# ── Initialize on import ─────────────────────────────────────────────────────
_init_db()
