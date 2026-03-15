"""
User Data Store — medication reminders + benefits usage tracking.

Stores persistent per-member data in a separate SQLite database (user_data.db),
independent from the read-only CMS benefits DB.

Members are identified by phone number (10-digit, no formatting).
API layer resolves session_id → phone before calling these methods.
"""

import hashlib
import hmac
import logging
import os
import sqlite3
import threading
from datetime import date, datetime
from typing import Optional

from .encryption import get_cipher

log = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
_PERSISTENT_DIR = "/data" if os.path.isdir("/data") else _PARENT_DIR
DEFAULT_USER_DB = os.path.join(_PERSISTENT_DIR, "user_data.db")


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
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass  # WAL already set or disk locked briefly — non-fatal
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

    # ── Phone hashing (deterministic, for WHERE lookups) ────────────────

    @staticmethod
    def _hash_phone(phone: str) -> str:
        """HMAC-SHA256 keyed hash of phone for indexed lookups (not reversible without key)."""
        key = os.environ.get("FIELD_ENCRYPTION_KEY", "dev-key").encode()
        return hmac.new(key, phone.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _encrypt_phone(phone: str) -> str:
        """Encrypt phone for at-rest storage (reversible with key)."""
        cipher = get_cipher()
        if cipher.enabled:
            return cipher.encrypt(phone)
        return phone

    @staticmethod
    def _decrypt_phone(value: str) -> str:
        """Decrypt phone value from DB."""
        cipher = get_cipher()
        if cipher.enabled:
            return cipher.decrypt(value)
        return value

    # ── Table creation ───────────────────────────────────────────────────

    def _ensure_tables(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS medication_reminders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
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
            CREATE INDEX IF NOT EXISTS idx_reminders_phone_hash
                ON medication_reminders(phone_hash);

            CREATE TABLE IF NOT EXISTS benefits_usage (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
                category        TEXT NOT NULL,
                amount          REAL NOT NULL,
                description     TEXT DEFAULT '',
                usage_date      TEXT NOT NULL,
                period_key      TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now')),
                created_by      TEXT DEFAULT 'member'
            );
            CREATE INDEX IF NOT EXISTS idx_usage_phone_hash
                ON benefits_usage(phone_hash);
            CREATE INDEX IF NOT EXISTS idx_usage_phone_hash_cat
                ON benefits_usage(phone_hash, category);

            CREATE TABLE IF NOT EXISTS health_screenings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
                gender          TEXT,
                answers_json    TEXT NOT NULL DEFAULT '{}',
                reminders_json  TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_screenings_phone_hash
                ON health_screenings(phone_hash);

            CREATE TABLE IF NOT EXISTS appointment_requests (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
                member_name     TEXT NOT NULL DEFAULT '',
                doctor_name     TEXT NOT NULL DEFAULT '',
                reason          TEXT DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'pending',
                agent_notes     TEXT DEFAULT '',
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_appt_phone_hash
                ON appointment_requests(phone_hash);
            CREATE INDEX IF NOT EXISTS idx_appt_status
                ON appointment_requests(status);

            CREATE TABLE IF NOT EXISTS adherence_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
                reminder_id     INTEGER NOT NULL,
                drug_name       TEXT NOT NULL,
                taken           INTEGER NOT NULL DEFAULT 1,
                logged_at       TEXT DEFAULT (datetime('now')),
                log_date        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_adherence_phone_hash
                ON adherence_logs(phone_hash);
            CREATE INDEX IF NOT EXISTS idx_adherence_reminder
                ON adherence_logs(phone_hash, reminder_id, log_date);

            CREATE TABLE IF NOT EXISTS sdoh_screenings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL DEFAULT '',
                transportation  TEXT NOT NULL DEFAULT 'no',
                food_insecurity TEXT NOT NULL DEFAULT 'no',
                social_isolation TEXT NOT NULL DEFAULT 'never',
                housing_stability TEXT NOT NULL DEFAULT 'no',
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_sdoh_phone_hash
                ON sdoh_screenings(phone_hash);
        """)
        # Add phone_hash column if upgrading from old schema
        try:
            conn.execute("ALTER TABLE medication_reminders ADD COLUMN phone_hash TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE benefits_usage ADD COLUMN phone_hash TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()
        log.info(f"User data DB ready at {self.db_path}")

    # ── Medication Reminders — CRUD ──────────────────────────────────────

    def get_reminders(self, phone: str) -> list[dict]:
        """Get all reminders for a member, ordered by time."""
        ph = self._hash_phone(phone)
        rows = self._query_all(
            "SELECT * FROM medication_reminders WHERE phone_hash = ? ORDER BY time_hour, time_minute, drug_name",
            (ph,),
        )
        for r in rows:
            r["phone"] = self._decrypt_phone(r["phone"])
        return rows

    def create_reminder(self, phone: str, drug_name: str, time_hour: int,
                        time_minute: int = 0, dose_label: str = "",
                        days_supply: int = 30, refill_reminder: bool = False,
                        last_refill_date: str = None, created_by: str = "member") -> dict:
        """Create a single reminder. Returns the new reminder."""
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        rid = self._execute(
            """INSERT INTO medication_reminders
               (phone, phone_hash, drug_name, dose_label, time_hour, time_minute,
                days_supply, refill_reminder, last_refill_date, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (enc_phone, ph, drug_name, dose_label, time_hour, time_minute,
             days_supply, int(refill_reminder), last_refill_date, created_by),
        )
        row = self._query_one("SELECT * FROM medication_reminders WHERE id = ?", (rid,))
        if row:
            row["phone"] = phone
        return row

    def create_reminders_bulk(self, phone: str, reminders: list[dict],
                              created_by: str = "member") -> list[dict]:
        """Create multiple reminders at once. Returns all new reminders."""
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        ids = []
        for r in reminders:
            rid = self._execute(
                """INSERT INTO medication_reminders
                   (phone, phone_hash, drug_name, dose_label, time_hour, time_minute,
                    days_supply, refill_reminder, last_refill_date, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (enc_phone, ph, r["drug_name"], r.get("dose_label", ""),
                 r["time_hour"], r.get("time_minute", 0),
                 r.get("days_supply", 30), int(r.get("refill_reminder", False)),
                 r.get("last_refill_date"), created_by),
            )
            ids.append(rid)
        rows = self._query_all(
            f"SELECT * FROM medication_reminders WHERE id IN ({','.join('?' * len(ids))}) ORDER BY time_hour, time_minute",
            tuple(ids),
        )
        for row in rows:
            row["phone"] = phone
        return rows

    def update_reminder(self, phone: str, reminder_id: int, **kwargs) -> Optional[dict]:
        """Update reminder fields. Only updates provided kwargs."""
        ph = self._hash_phone(phone)
        allowed = {"enabled", "time_hour", "time_minute", "refill_reminder",
                    "last_refill_date", "dose_label", "drug_name", "days_supply"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            row = self._query_one(
                "SELECT * FROM medication_reminders WHERE id = ? AND phone_hash = ?",
                (reminder_id, ph),
            )
            if row:
                row["phone"] = phone
            return row
        # Convert booleans to int for SQLite
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])
        if "refill_reminder" in updates:
            updates["refill_reminder"] = int(updates["refill_reminder"])
        updates["updated_at"] = datetime.utcnow().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [reminder_id, ph]
        self._execute(
            f"UPDATE medication_reminders SET {set_clause} WHERE id = ? AND phone_hash = ?",
            tuple(values),
        )
        row = self._query_one(
            "SELECT * FROM medication_reminders WHERE id = ? AND phone_hash = ?",
            (reminder_id, ph),
        )
        if row:
            row["phone"] = phone
        return row

    def delete_reminder(self, phone: str, reminder_id: int) -> bool:
        """Delete a reminder. Returns True if deleted."""
        ph = self._hash_phone(phone)
        count = self._execute_delete(
            "DELETE FROM medication_reminders WHERE id = ? AND phone_hash = ?",
            (reminder_id, ph),
        )
        return count > 0

    # ── Benefits Usage — CRUD ────────────────────────────────────────────

    def log_usage(self, phone: str, category: str, amount: float,
                  benefit_period: str = "Monthly", description: str = "",
                  usage_date: str = None, created_by: str = "member") -> dict:
        """Log a benefits usage entry. Returns the new entry."""
        if usage_date is None:
            usage_date = date.today().isoformat()
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        period_key = self._compute_period_key(usage_date, benefit_period)
        uid = self._execute(
            """INSERT INTO benefits_usage
               (phone, phone_hash, category, amount, description, usage_date, period_key, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (enc_phone, ph, category.lower(), amount, description, usage_date, period_key, created_by),
        )
        row = self._query_one("SELECT * FROM benefits_usage WHERE id = ?", (uid,))
        if row:
            row["phone"] = phone
        return row

    def get_usage(self, phone: str, category: str = None) -> list[dict]:
        """Get all usage entries, optionally filtered by category."""
        ph = self._hash_phone(phone)
        if category:
            rows = self._query_all(
                "SELECT * FROM benefits_usage WHERE phone_hash = ? AND category = ? ORDER BY usage_date DESC",
                (ph, category.lower()),
            )
        else:
            rows = self._query_all(
                "SELECT * FROM benefits_usage WHERE phone_hash = ? ORDER BY usage_date DESC",
                (ph,),
            )
        for r in rows:
            r["phone"] = self._decrypt_phone(r["phone"])
        return rows

    def get_usage_totals(self, phone: str, period_key: str = None) -> dict:
        """
        Get spending totals per category for a given period.
        If no period_key, returns totals for all current periods.
        Returns: {category: total_spent}
        """
        ph = self._hash_phone(phone)
        if period_key:
            rows = self._query_all(
                """SELECT category, SUM(amount) as total
                   FROM benefits_usage WHERE phone_hash = ? AND period_key = ?
                   GROUP BY category""",
                (ph, period_key),
            )
        else:
            rows = self._query_all(
                """SELECT category, SUM(amount) as total
                   FROM benefits_usage WHERE phone_hash = ?
                   GROUP BY category, period_key
                   ORDER BY category""",
                (ph,),
            )
        return {r["category"]: round(r["total"], 2) for r in rows}

    def get_current_period_totals(self, phone: str, benefit_periods: dict) -> dict:
        """
        Get spending totals for each category's *current* period.
        benefit_periods: {category: period_type} e.g. {"otc": "Monthly", "dental": "Yearly"}
        Returns: {category: total_spent}
        """
        ph = self._hash_phone(phone)
        today = date.today().isoformat()
        result = {}
        for cat, period_type in benefit_periods.items():
            period_key = self._compute_period_key(today, period_type)
            row = self._query_one(
                """SELECT SUM(amount) as total
                   FROM benefits_usage WHERE phone_hash = ? AND category = ? AND period_key = ?""",
                (ph, cat, period_key),
            )
            result[cat] = round(row["total"], 2) if row and row["total"] else 0.0
        return result

    def delete_usage(self, phone: str, usage_id: int) -> bool:
        """Delete a usage entry. Returns True if deleted."""
        ph = self._hash_phone(phone)
        count = self._execute_delete(
            "DELETE FROM benefits_usage WHERE id = ? AND phone_hash = ?",
            (usage_id, ph),
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

    # ── Health Screenings ──────────────────────────────────────────────

    def save_health_screenings(self, phone: str, data: dict):
        """Save a member's screening answers and generated reminders."""
        import json
        ph = self._hash_phone(phone)
        enc_phone = self._encrypt_phone(phone)
        self._execute(
            """INSERT INTO health_screenings (phone, phone_hash, gender, answers_json, reminders_json)
               VALUES (?, ?, ?, ?, ?)""",
            (enc_phone, ph, data.get("gender", ""),
             json.dumps(data.get("answers", {})),
             json.dumps(data.get("reminders", []))),
        )

    def get_health_screenings(self, phone: str) -> dict | None:
        """Get most recent screening submission for a member."""
        import json
        ph = self._hash_phone(phone)
        row = self._query_one(
            "SELECT * FROM health_screenings WHERE phone_hash = ? ORDER BY created_at DESC LIMIT 1",
            (ph,),
        )
        if not row:
            return None
        return {
            "gender": row["gender"],
            "answers": json.loads(row["answers_json"]),
            "reminders": json.loads(row["reminders_json"]),
            "created_at": row["created_at"],
        }

    def get_health_screening_history(self, phone: str) -> list[dict]:
        """Get all screening submissions for a member, most recent first."""
        import json
        ph = self._hash_phone(phone)
        rows = self._query_all(
            "SELECT * FROM health_screenings WHERE phone_hash = ? ORDER BY created_at DESC",
            (ph,),
        )
        results = []
        for r in rows:
            answers = json.loads(r["answers_json"])
            # Compute gaps (screenings answered 'no' or False)
            gaps = [k for k, v in answers.items() if v is False or v == "no"]
            completed = [k for k, v in answers.items() if v is True or v == "yes"]
            results.append({
                "id": r["id"],
                "gender": r["gender"],
                "answers": answers,
                "gaps": gaps,
                "completed": completed,
                "gap_count": len(gaps),
                "completed_count": len(completed),
                "total_count": len(answers),
                "created_at": r["created_at"],
            })
        return results

    def get_sdoh_screening_history(self, phone: str) -> list[dict]:
        """Get all SDOH screening submissions for a member, most recent first."""
        ph = self._hash_phone(phone)
        rows = self._query_all(
            "SELECT * FROM sdoh_screenings WHERE phone_hash = ? ORDER BY created_at DESC",
            (ph,),
        )
        results = []
        for r in rows:
            flags = []
            if r["transportation"] == "yes":
                flags.append("Transportation")
            if r["food_insecurity"] == "yes":
                flags.append("Food Access")
            if r["social_isolation"] in ("sometimes", "often", "always"):
                flags.append("Social Isolation")
            if r["housing_stability"] == "yes":
                flags.append("Housing")
            results.append({
                "id": r["id"],
                "transportation": r["transportation"],
                "food_insecurity": r["food_insecurity"],
                "social_isolation": r["social_isolation"],
                "housing_stability": r["housing_stability"],
                "flags": flags,
                "flag_count": len(flags),
                "created_at": r["created_at"],
            })
        return results

    # ── Appointment Requests ───────────────────────────────────────────

    def create_appointment_request(self, phone: str, member_name: str,
                                   doctor_name: str, reason: str = "") -> int:
        """Create a new appointment request and return its ID."""
        ph = self._hash_phone(phone)
        enc_phone = self._encrypt_phone(phone)
        return self._execute(
            """INSERT INTO appointment_requests
               (phone, phone_hash, member_name, doctor_name, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (enc_phone, ph, member_name, doctor_name, reason),
        )

    def list_appointment_requests(self, status: str = None,
                                  limit: int = 50, offset: int = 0) -> list[dict]:
        """List appointment requests, optionally filtered by status."""
        if status:
            rows = self._query_all(
                """SELECT id, phone, member_name, doctor_name, reason, status,
                          agent_notes, created_at, updated_at
                   FROM appointment_requests WHERE status = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (status, limit, offset),
            )
        else:
            rows = self._query_all(
                """SELECT id, phone, member_name, doctor_name, reason, status,
                          agent_notes, created_at, updated_at
                   FROM appointment_requests
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        # Decrypt phone for admin display
        for r in rows:
            r["phone"] = self._decrypt_phone(r["phone"])
        return rows

    def update_appointment_request(self, request_id: int, status: str = None,
                                   agent_notes: str = None) -> dict | None:
        """Update an appointment request status and/or notes."""
        fields = []
        params = []
        if status:
            fields.append("status = ?")
            params.append(status)
        if agent_notes is not None:
            fields.append("agent_notes = ?")
            params.append(agent_notes)
        if not fields:
            return None
        fields.append("updated_at = datetime('now')")
        params.append(request_id)
        self._execute(
            f"UPDATE appointment_requests SET {', '.join(fields)} WHERE id = ?",
            tuple(params),
        )
        row = self._query_one("SELECT * FROM appointment_requests WHERE id = ?", (request_id,))
        if not row:
            return None
        row = dict(row)
        row["phone"] = self._decrypt_phone(row["phone"])
        return row

    # ── Adherence Tracking ──────────────────────────────────────────

    def log_adherence(self, phone: str, reminder_id: int, drug_name: str,
                      taken: bool = True, log_date: str = None) -> dict:
        """Log that a member took (or missed) a medication dose."""
        if log_date is None:
            log_date = date.today().isoformat()
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        aid = self._execute(
            """INSERT INTO adherence_logs
               (phone, phone_hash, reminder_id, drug_name, taken, log_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (enc_phone, ph, reminder_id, drug_name, int(taken), log_date),
        )
        row = self._query_one("SELECT * FROM adherence_logs WHERE id = ?", (aid,))
        if row:
            row["phone"] = phone
        return row

    def get_adherence_summary(self, phone: str, days: int = 30) -> list[dict]:
        """
        Get adherence summary per medication for the last N days.
        Returns: [{reminder_id, drug_name, doses_taken, doses_missed, total_days, adherence_pct}]
        """
        ph = self._hash_phone(phone)
        rows = self._query_all(
            """SELECT reminder_id, drug_name,
                      SUM(CASE WHEN taken = 1 THEN 1 ELSE 0 END) as doses_taken,
                      SUM(CASE WHEN taken = 0 THEN 1 ELSE 0 END) as doses_missed,
                      COUNT(*) as total_days
               FROM adherence_logs
               WHERE phone_hash = ? AND log_date >= date('now', ?)
               GROUP BY reminder_id, drug_name
               ORDER BY drug_name""",
            (ph, f"-{days} days"),
        )
        result = []
        for r in rows:
            total = r["total_days"]
            pct = round((r["doses_taken"] / total) * 100, 1) if total > 0 else 0
            result.append({
                "reminder_id": r["reminder_id"],
                "drug_name": r["drug_name"],
                "doses_taken": r["doses_taken"],
                "doses_missed": r["doses_missed"],
                "total_days": total,
                "adherence_pct": pct,
            })
        return result

    def get_adherence_for_date(self, phone: str, log_date: str) -> list[dict]:
        """Get all adherence logs for a specific date."""
        ph = self._hash_phone(phone)
        return self._query_all(
            "SELECT * FROM adherence_logs WHERE phone_hash = ? AND log_date = ?",
            (ph, log_date),
        )

    def get_refill_alerts(self, phone: str) -> list[dict]:
        """
        Get reminders where refill_reminder is enabled and the refill is due
        (last_refill_date + days_supply <= today + 3 days).
        """
        ph = self._hash_phone(phone)
        rows = self._query_all(
            """SELECT * FROM medication_reminders
               WHERE phone_hash = ? AND enabled = 1 AND refill_reminder = 1
                     AND last_refill_date IS NOT NULL
                     AND date(last_refill_date, '+' || days_supply || ' days') <= date('now', '+3 days')
               ORDER BY date(last_refill_date, '+' || days_supply || ' days')""",
            (ph,),
        )
        today = date.today()
        result = []
        for r in rows:
            r["phone"] = self._decrypt_phone(r["phone"])
            try:
                refill_date = datetime.strptime(r["last_refill_date"], "%Y-%m-%d").date()
                due_date = refill_date + __import__("datetime").timedelta(days=r["days_supply"])
                r["refill_due_date"] = due_date.isoformat()
                r["days_until_refill"] = (due_date - today).days
            except (ValueError, TypeError):
                r["refill_due_date"] = None
                r["days_until_refill"] = None
            result.append(r)
        return result

    # ── SDoH Screening ────────────────────────────────────────────

    def save_sdoh_screening(self, phone: str, data: dict) -> dict:
        """Save a member's SDoH screening answers."""
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        sid = self._execute(
            """INSERT INTO sdoh_screenings
               (phone, phone_hash, transportation, food_insecurity,
                social_isolation, housing_stability)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (enc_phone, ph,
             data.get("transportation", "no"),
             data.get("food_insecurity", "no"),
             data.get("social_isolation", "never"),
             data.get("housing_stability", "no")),
        )
        row = self._query_one("SELECT * FROM sdoh_screenings WHERE id = ?", (sid,))
        if row:
            row["phone"] = phone
        return row

    def get_sdoh_screening(self, phone: str) -> dict | None:
        """Get most recent SDoH screening for a member."""
        ph = self._hash_phone(phone)
        row = self._query_one(
            "SELECT * FROM sdoh_screenings WHERE phone_hash = ? ORDER BY created_at DESC LIMIT 1",
            (ph,),
        )
        if not row:
            return None
        row = dict(row)
        row["phone"] = self._decrypt_phone(row["phone"])
        return row

    def get_all_sdoh_results(self) -> list[dict]:
        """Get all SDoH submissions for admin reporting (latest per member)."""
        rows = self._query_all(
            "SELECT * FROM sdoh_screenings ORDER BY created_at DESC"
        )
        seen = set()
        results = []
        for r in rows:
            ph = r["phone_hash"]
            if ph in seen:
                continue
            seen.add(ph)
            flags = []
            if r["transportation"] == "yes":
                flags.append("transportation")
            if r["food_insecurity"] == "yes":
                flags.append("food_insecurity")
            if r["social_isolation"] in ("sometimes", "often", "always"):
                flags.append("social_isolation")
            if r["housing_stability"] == "yes":
                flags.append("housing_stability")
            results.append({
                "phone_last4": self._decrypt_phone(r["phone"])[-4:],
                "transportation": r["transportation"],
                "food_insecurity": r["food_insecurity"],
                "social_isolation": r["social_isolation"],
                "housing_stability": r["housing_stability"],
                "flags": flags,
                "flag_count": len(flags),
                "created_at": r["created_at"],
            })
        return results

    # ── Health Screening Gap Report (Admin) ─────────────────────────

    def get_all_screening_results(self) -> list[dict]:
        """Get all screening submissions for gap analysis."""
        import json
        rows = self._query_all(
            """SELECT phone, phone_hash, gender, answers_json, reminders_json, created_at
               FROM health_screenings ORDER BY created_at DESC"""
        )
        seen = set()
        results = []
        for r in rows:
            ph = r["phone_hash"]
            if ph in seen:
                continue  # Only latest per member
            seen.add(ph)
            results.append({
                "phone_last4": self._decrypt_phone(r["phone"])[-4:],
                "gender": r["gender"],
                "answers": json.loads(r["answers_json"]),
                "reminders": json.loads(r["reminders_json"]),
                "created_at": r["created_at"],
            })
        return results

    # ── MTM Eligibility ─────────────────────────────────────────────

    def get_reminder_count(self, phone: str) -> int:
        """Get count of active medication reminders for a member."""
        ph = self._hash_phone(phone)
        row = self._query_one(
            "SELECT COUNT(*) as cnt FROM medication_reminders WHERE phone_hash = ? AND enabled = 1",
            (ph,),
        )
        return row["cnt"] if row else 0

    def count_appointment_requests(self, status: str = None) -> int:
        """Count appointment requests, optionally by status."""
        if status:
            row = self._query_one(
                "SELECT COUNT(*) as cnt FROM appointment_requests WHERE status = ?",
                (status,),
            )
        else:
            row = self._query_one("SELECT COUNT(*) as cnt FROM appointment_requests")
        return row["cnt"] if row else 0

    # ── Secure Messaging ──────────────────────────────────────────────

    def _ensure_messages_table(self):
        """Create messages table if not present (lazy migration)."""
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                phone_hash      TEXT NOT NULL,
                sender_type     TEXT NOT NULL DEFAULT 'agent',
                sender_name     TEXT NOT NULL DEFAULT '',
                body            TEXT NOT NULL,
                read            INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_msg_phone_hash
                ON messages(phone_hash);
        """)
        conn.commit()

    def send_message(self, phone: str, sender_type: str, sender_name: str,
                     body: str) -> dict:
        """Insert a message in the thread. sender_type: 'agent' or 'member'."""
        self._ensure_messages_table()
        enc_phone = self._encrypt_phone(phone)
        ph = self._hash_phone(phone)
        mid = self._execute(
            """INSERT INTO messages (phone, phone_hash, sender_type, sender_name, body)
               VALUES (?, ?, ?, ?, ?)""",
            (enc_phone, ph, sender_type, sender_name, body),
        )
        row = self._query_one("SELECT * FROM messages WHERE id = ?", (mid,))
        return dict(row) if row else {"id": mid}

    def get_messages(self, phone: str, limit: int = 50) -> list[dict]:
        """Get conversation thread for a member, most recent last."""
        self._ensure_messages_table()
        ph = self._hash_phone(phone)
        rows = self._query_all(
            "SELECT id, sender_type, sender_name, body, read, created_at FROM messages WHERE phone_hash = ? ORDER BY created_at ASC LIMIT ?",
            (ph, limit),
        )
        return [dict(r) for r in rows]

    def mark_messages_read(self, phone: str, sender_type: str) -> int:
        """Mark all messages from a given sender_type as read. Returns count."""
        self._ensure_messages_table()
        ph = self._hash_phone(phone)
        conn = self._conn()
        cursor = conn.execute(
            "UPDATE messages SET read = 1 WHERE phone_hash = ? AND sender_type = ? AND read = 0",
            (ph, sender_type),
        )
        conn.commit()
        return cursor.rowcount

    def get_unread_count(self, phone: str, sender_type: str) -> int:
        """Count unread messages from a given sender type."""
        self._ensure_messages_table()
        ph = self._hash_phone(phone)
        row = self._query_one(
            "SELECT COUNT(*) as cnt FROM messages WHERE phone_hash = ? AND sender_type = ? AND read = 0",
            (ph, sender_type),
        )
        return row["cnt"] if row else 0

    def get_all_conversations(self) -> list[dict]:
        """Get summary of all conversations for admin inbox view."""
        self._ensure_messages_table()
        rows = self._query_all("""
            SELECT phone_hash,
                   MAX(created_at) as last_message_at,
                   COUNT(*) as total_messages,
                   SUM(CASE WHEN sender_type = 'member' AND read = 0 THEN 1 ELSE 0 END) as unread_from_member
            FROM messages
            GROUP BY phone_hash
            ORDER BY MAX(created_at) DESC
        """)
        return [dict(r) for r in rows]
