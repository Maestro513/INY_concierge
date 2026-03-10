#!/usr/bin/env bash
# Database backup script for HIPAA-compliant PHI data protection.
#
# Usage:
#   bash scripts/backup_db.sh              # one-time backup
#   cron: 0 */6 * * * /app/backend/scripts/backup_db.sh   # every 6 hours
#
# Backs up all mutable SQLite databases to a timestamped directory.
# Uses SQLite's .backup command (safe for concurrent access — no locking issues).
# Retains the last 7 days of backups by default.

set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
BACKUP_DIR="${BACKUP_DIR:-${DATA_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
DEST="${BACKUP_DIR}/${TIMESTAMP}"

DBS=(
    "persistent_store.db"
    "audit.db"
    "admin.db"
    "user_data.db"
)

mkdir -p "$DEST"

BACKED_UP=0
ERRORS=0

for db in "${DBS[@]}"; do
    src="${DATA_DIR}/${db}"
    if [ -f "$src" ]; then
        echo "Backing up ${db} ..."
        if sqlite3 "$src" ".backup '${DEST}/${db}'"; then
            BACKED_UP=$((BACKED_UP + 1))
        else
            echo "ERROR: Failed to back up ${db}" >&2
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "SKIP: ${db} not found at ${src}"
    fi
done

echo "Backed up ${BACKED_UP} databases to ${DEST} (${ERRORS} errors)"

# Prune old backups
if [ -d "$BACKUP_DIR" ]; then
    find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true
    REMAINING=$(find "$BACKUP_DIR" -maxdepth 1 -type d | wc -l)
    echo "Pruned backups older than ${RETENTION_DAYS} days. ${REMAINING} backup(s) retained."
fi

exit $ERRORS
