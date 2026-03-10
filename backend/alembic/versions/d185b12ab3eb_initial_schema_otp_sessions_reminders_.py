"""initial schema - otp sessions reminders usage

Revision ID: d185b12ab3eb
Revises:
Create Date: 2026-03-05 03:18:01.109499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd185b12ab3eb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all application tables (idempotent for existing databases)."""

    # ── Persistent Store: OTP ─────────────────────────────────────────
    op.create_table(
        "otp_store",
        sa.Column("phone", sa.Text, primary_key=True),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("ttl", sa.Integer, nullable=False, server_default="300"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.Float, nullable=False, server_default="0"),
        if_not_exists=True,
    )

    op.create_table(
        "otp_send_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Float, nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "idx_otp_send_phone", "otp_send_log", ["phone", "sent_at"],
        if_not_exists=True,
    )

    # ── Persistent Store: Sessions ────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text, primary_key=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "idx_sessions_phone", "sessions", ["phone"],
        if_not_exists=True,
    )

    # ── User Data: Medication Reminders ───────────────────────────────
    op.create_table(
        "medication_reminders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("drug_name", sa.Text, nullable=False),
        sa.Column("dose_label", sa.Text, server_default=""),
        sa.Column("time_hour", sa.Integer, nullable=False),
        sa.Column("time_minute", sa.Integer, nullable=False, server_default="0"),
        sa.Column("days_supply", sa.Integer, server_default="30"),
        sa.Column("refill_reminder", sa.Integer, server_default="0"),
        sa.Column("last_refill_date", sa.Text),
        sa.Column("enabled", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.Text, server_default=sa.text("(datetime('now'))")),
        sa.Column("updated_at", sa.Text, server_default=sa.text("(datetime('now'))")),
        sa.Column("created_by", sa.Text, server_default="member"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_reminders_phone", "medication_reminders", ["phone"],
        if_not_exists=True,
    )

    # ── User Data: Benefits Usage ─────────────────────────────────────
    op.create_table(
        "benefits_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("usage_date", sa.Text, nullable=False),
        sa.Column("period_key", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, server_default=sa.text("(datetime('now'))")),
        sa.Column("created_by", sa.Text, server_default="member"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_usage_phone", "benefits_usage", ["phone"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_usage_phone_cat", "benefits_usage", ["phone", "category"],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop all application tables."""
    op.drop_table("benefits_usage")
    op.drop_table("medication_reminders")
    op.drop_table("sessions")
    op.drop_table("otp_send_log")
    op.drop_table("otp_store")
