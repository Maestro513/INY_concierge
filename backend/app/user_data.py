"""
User Data Store — medication reminders + benefits usage tracking.

Stores persistent per-member data in a separate SQLite database (user_data.db),
independent from the read-only CMS benefits DB.

Members are identified by phone number (10-digit, no formatting).
API layer resolves session_id → phone before calling these methods.
"""

import sqlite3
import os
import logging
import threading
from datetime import datetime, date
from typing import Optional

log = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
DEFAULT_USER_DB = os.path.join(_PARENT_DIR, "user_data.db")


class UserDataDB:
    """CRUD operations for medication reminders and benefits usage."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("USER_DB_PATH", DEFAULT_USER_DB)
        self._local = threading.local()
        self._ensure_tables()

    # ── Connection pooling (thread-local, same pattern as CMSLookup) ─────

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
            self._local.conn = conn
        return conn

    def _query_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def _query_all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE and return lastrowid."""
        with self._conn() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.lastrowid

    def _execute_delete(self, sql: str, params: tuple = ()) -> int:
        """Execute a DELETE and return number of rows affected."""
        with self._conn() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount

    # ── Table creation ───────────────────────────────────────────────────

    def _ensure_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS medication_reminders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                drug_name       TEXT NOT NULL,
                dose_label      TEXT DEFAULT '',
                time_hour       INTEGER NOT NULL,
                time_minute     INTEGER NOT NULL DEFAULT 0,
                days_supply     INTEGER DEFAULT 30,
                refill_reminder INTEGER DEFAULT 0,
                last_refill_date TEXT,
                enabled         INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now')),
                created_by      TEXT DEFAULT 'member'
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_phone
                ON medication_reminders(phone);

            CREATE TABLE IF NOT EXISTS benefits_usage (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                category        TEXT NOT NULL,
                amount          REAL NOT NULL,
                description     TEXT DEFAULT '',
                usage_date      TEXT NOT NULL,
                period_key      TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now')),
                created_by      TEXT DEFAULT 'member'
            );
            CREATE INDEX IF NOT EXISTS idx_usage_phone
                ON benefits_usage(phone);
            CREATE INDEX IF NOT EXISTS idx_usage_phone_cat
                ON benefits_usage(phone, category);
        """)
        conn.commit()
        log.info(f"User data DB ready at {self.db_path}")

    # ── Medication Reminders — CRUD ──────────────────────────────────────

    def get_reminders(self, phone: str) -> list[dict]:
        """Get all reminders for a member, ordered by time."""
        return self._query_all(
            "SELECT * FROM medication_reminders WHERE phone = ? ORDER BY time_hour, time_minute, drug_name",
            (phone,),
        )

    def create_reminder(self, phone: str, drug_name: str, time_hour: int,
                        time_minute: int = 0, dose_label: str = "",
                        days_supply: int = 30, refill_reminder: bool = False,
                        last_refill_date: str = None, created_by: str = "member") -> dict:
        """Create a single reminder. Returns the new reminder."""
        rid = self._execute(
            """INSERT INTO medication_reminders
               (phone, drug_name, dose_label, time_hour, time_minute,
                days_supply, refill_reminder, last_refill_date, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (phone, drug_name, dose_label, time_hour, time_minute,
             days_supply, int(refill_reminder), last_refill_date, created_by),
        )
        return self._query_one("SELECT * FROM medication_reminders WHERE id = ?", (rid,))

    def create_reminders_bulk(self, phone: str, reminders: list[dict],
                              created_by: str = "member") -> list[dict]:
        """Create multiple reminders at once. Returns all new reminders."""
        ids = []
        for r in reminders:
            rid = self._execute(
                """INSERT INTO medication_reminders
                   (phone, drug_name, dose_label, time_hour, time_minute,
                    days_supply, refill_reminder, last_refill_date, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (phone, r["drug_name"], r.get("dose_label", ""),
                 r["time_hour"], r.get("time_minute", 0),
                 r.get("days_supply", 30), int(r.get("refill_reminder", False)),
                 r.get("last_refill_date"), created_by),
            )
            ids.append(rid)
        return self._query_all(
            f"SELECT * FROM medication_reminders WHERE id IN ({','.join('?' * len(ids))}) ORDER BY time_hour, time_minute",
            tuple(ids),
        )

    def update_reminder(self, phone: str, reminder_id: int, **kwargs) -> Optional[dict]:
        """Update reminder fields. Only updates provided kwargs."""
        allowed = {"enabled", "time_hour", "time_minute", "refill_reminder",
                    "last_refill_date", "dose_label", "drug_name", "days_supply"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return self._query_one(
                "SELECT * FROM medication_reminders WHERE id = ? AND phone = ?",
                (reminder_id, phone),
            )
        # Convert booleans to int for SQLite
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])
        if "refill_reminder" in updates:
            updates["refill_reminder"] = int(updates["refill_reminder"])
        updates["updated_at"] = datetime.utcnow().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [reminder_id, phone]
        self._execute(
            f"UPDATE medication_reminders SET {set_clause} WHERE id = ? AND phone = ?",
            tuple(values),
        )
        return self._query_one(
            "SELECT * FROM medication_reminders WHERE id = ? AND phone = ?",
            (reminder_id, phone),
        )

    def delete_reminder(self, phone: str, reminder_id: int) -> bool:
        """Delete a reminder. Returns True if deleted."""
        count = self._execute_delete(
            "DELETE FROM medication_reminders WHERE id = ? AND phone = ?",
            (reminder_id, phone),
        )
        return count > 0

    # ── Benefits Usage — CRUD ────────────────────────────────────────────

    def log_usage(self, phone: str, category: str, amount: float,
                  benefit_period: str = "Monthly", description: str = "",
                  usage_date: str = None, created_by: str = "member") -> dict:
        """Log a benefits usage entry. Returns the new entry."""
        if usage_date is None:
            usage_date = date.today().isoformat()
        period_key = self._compute_period_key(usage_date, benefit_period)
        uid = self._execute(
            """INSERT INTO benefits_usage
               (phone, category, amount, description, usage_date, period_key, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (phone, category.lower(), amount, description, usage_date, period_key, created_by),
        )
        return self._query_one("SELECT * FROM benefits_usage WHERE id = ?", (uid,))

    def get_usage(self, phone: str, category: str = None) -> list[dict]:
        """Get all usage entries, optionally filtered by category."""
        if category:
            return self._query_all(
                "SELECT * FROM benefits_usage WHERE phone = ? AND category = ? ORDER BY usage_date DESC",
                (phone, category.lower()),
            )
        return self._query_all(
            "SELECT * FROM benefits_usage WHERE phone = ? ORDER BY usage_date DESC",
            (phone,),
        )

    def get_usage_totals(self, phone: str, period_key: str = None) -> dict:
        """
        Get spending totals per category for a given period.
        If no period_key, returns totals for all current periods.
        Returns: {category: total_spent}
        """
        if period_key:
            rows = self._query_all(
                """SELECT category, SUM(amount) as total
                   FROM benefits_usage WHERE phone = ? AND period_key = ?
                   GROUP BY category""",
                (phone, period_key),
            )
        else:
            # Get totals for each category's current period
            rows = self._query_all(
                """SELECT category, SUM(amount) as total
                   FROM benefits_usage WHERE phone = ?
                   GROUP BY category, period_key
                   ORDER BY category""",
                (phone,),
            )
        return {r["category"]: round(r["total"], 2) for r in rows}

    def get_current_period_totals(self, phone: str, benefit_periods: dict) -> dict:
        """
        Get spending totals for each category's *current* period.
        benefit_periods: {category: period_type} e.g. {"otc": "Monthly", "dental": "Yearly"}
        Returns: {category: total_spent}
        """
        today = date.today().isoformat()
        result = {}
        for cat, period_type in benefit_periods.items():
            period_key = self._compute_period_key(today, period_type)
            row = self._query_one(
                """SELECT SUM(amount) as total
                   FROM benefits_usage WHERE phone = ? AND category = ? AND period_key = ?""",
                (phone, cat, period_key),
            )
            result[cat] = round(row["total"], 2) if row and row["total"] else 0.0
        return result

    def delete_usage(self, phone: str, usage_id: int) -> bool:
        """Delete a usage entry. Returns True if deleted."""
        count = self._execute_delete(
            "DELETE FROM benefits_usage WHERE id = ? AND phone = ?",
            (usage_id, phone),
        )
        return count > 0

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_period_key(usage_date: str, benefit_period: str) -> str:
        """
        Compute period key from date + benefit period type.
        Monthly → "2026-01", Quarterly → "2026-Q1", Yearly → "2026"
        """
        dt = datetime.strptime(usage_date, "%Y-%m-%d")
        period = benefit_period.lower()
        if period == "monthly":
            return f"{dt.year}-{dt.month:02d}"
        elif period == "quarterly":
            q = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{q}"
        else:  # yearly or anything else
            return str(dt.year)
