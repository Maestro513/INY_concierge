"""
PR14: Database migration runner.

Runs schema migrations on startup, replacing fragile
CREATE TABLE IF NOT EXISTS + ALTER TABLE try/except patterns.

Each migration is idempotent — safe to re-run on every deploy.
"""

import logging
import os
import sqlite3

log = logging.getLogger(__name__)

# All known databases and their expected schemas
_PERSISTENT_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Get column names for a table."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1] for r in rows}
    except sqlite3.OperationalError:
        return set()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate_persistent_store(db_path: str | None = None):
    """Run migrations on the persistent store DB."""
    if db_path is None:
        db_path = os.environ.get(
            "STORE_DB_PATH",
            os.path.join(_PERSISTENT_DIR, "persistent_store.db"),
        )

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.OperationalError:
        pass

    # Ensure worker_metrics table exists (added after initial schema)
    if not _table_exists(conn, "worker_metrics"):
        conn.execute("""
            CREATE TABLE worker_metrics (
                worker_id   TEXT PRIMARY KEY,
                total       INTEGER NOT NULL DEFAULT 0,
                errors      INTEGER NOT NULL DEFAULT 0,
                latency_sum REAL NOT NULL DEFAULT 0.0,
                updated_at  REAL NOT NULL
            )
        """)
        log.info("Created worker_metrics table")

    conn.commit()
    conn.close()
    log.info("persistent_store.db migrations complete")


def migrate_admin_db(db_path: str | None = None):
    """Run migrations on the admin DB."""
    if db_path is None:
        db_dir = os.environ.get("DATA_DIR", _PERSISTENT_DIR)
        db_path = os.path.join(db_dir, "admin.db")

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.OperationalError:
        pass

    # Ensure login_events has user_agent column (added later)
    if _table_exists(conn, "login_events"):
        cols = _get_columns(conn, "login_events")
        if "user_agent" not in cols:
            conn.execute("ALTER TABLE login_events ADD COLUMN user_agent TEXT DEFAULT ''")
            log.info("Added user_agent column to login_events")

    conn.commit()
    conn.close()
    log.info("admin.db migrations complete")


def migrate_audit_db(db_path: str | None = None):
    """Run migrations on the audit DB."""
    if db_path is None:
        db_path = os.environ.get(
            "AUDIT_DB_PATH",
            os.path.join(_PERSISTENT_DIR, "audit.db"),
        )

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.OperationalError:
        pass

    # Ensure detail column exists (added after initial schema)
    if _table_exists(conn, "audit_log"):
        cols = _get_columns(conn, "audit_log")
        if "detail" not in cols:
            conn.execute("ALTER TABLE audit_log ADD COLUMN detail TEXT DEFAULT ''")
            log.info("Added detail column to audit_log")

    conn.commit()
    conn.close()
    log.info("audit.db migrations complete")


def run_all():
    """Run all database migrations. Called from start.sh before server starts."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("Running database migrations...")
    migrate_persistent_store()
    migrate_admin_db()
    migrate_audit_db()
    log.info("All migrations complete.")


if __name__ == "__main__":
    run_all()
