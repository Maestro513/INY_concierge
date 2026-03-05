"""
Alembic environment for INY Concierge SQLite databases.

Manages schema migrations for:
  - persistent_store.db (OTP + sessions)
  - user_data.db (reminders + usage tracking)

Both databases share the same migration history since they're
part of the same application. Tables are created idempotently
so migrations only run ALTER/ADD operations.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

# Resolve the database URL from environment or default
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_default_db = os.path.join(_backend_dir, "persistent_store.db")
_db_path = os.environ.get("ALEMBIC_DB_PATH", _default_db)
_db_url = f"sqlite:///{_db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
