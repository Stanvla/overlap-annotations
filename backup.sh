#!/usr/bin/env bash
# Simple backup script for the annotations database.
# Run manually or via cron:
#   crontab -e
#   0 */6 * * * /path/to/overlap-annotations/backup.sh
#
# Keeps the last 10 backups.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_FILE="$SCRIPT_DIR/annotations.db"
BACKUP_DIR="$SCRIPT_DIR/backups"
MAX_BACKUPS=10

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
