#!/usr/bin/env bash
# Simple backup script for the annotations database.
# Run manually or via cron:
#   crontab -e
#   0 */6 * * * /path/to/overlap-annotations/backup.sh
#
# Optional environment variables:
#   ANNOTATION_DB — database path (default: ./annotations.db relative to this script)
#   BACKUP_DIR    — backup directory (default: ./backups relative to this script)
#
# Keeps the last 10 backups.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RAW_DB_FILE="${ANNOTATION_DB:-annotations.db}"
RAW_BACKUP_DIR="${BACKUP_DIR:-backups}"
MAX_BACKUPS=10

if [[ "$RAW_DB_FILE" = /* ]]; then
    DB_FILE="$RAW_DB_FILE"
else
    DB_FILE="$SCRIPT_DIR/$RAW_DB_FILE"
fi

if [[ "$RAW_BACKUP_DIR" = /* ]]; then
    BACKUP_DIR="$RAW_BACKUP_DIR"
else
    BACKUP_DIR="$SCRIPT_DIR/$RAW_BACKUP_DIR"
fi

if ! command -v sqlite3 &>/dev/null; then
    echo "sqlite3 command not found. Install sqlite3 to use backup.sh."
    exit 1
fi

if [ ! -f "$DB_FILE" ]; then
    echo "No database file found at $DB_FILE"
    exit 0
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/annotations_${TIMESTAMP}.db"

# Use SQLite's .backup command for a safe copy (handles WAL correctly)
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

echo "Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Remove old backups, keep only the latest MAX_BACKUPS
cd "$BACKUP_DIR"
ls -1t annotations_*.db 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm --
echo "Backups retained: $(ls -1 annotations_*.db 2>/dev/null | wc -l)/$MAX_BACKUPS"
