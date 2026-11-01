#!/bin/bash
#
# KiboLens Automated Backup Script
# Place in /etc/cron.daily/kibolens-backup for daily execution
#
# SECURITY NOTES:
# - Backups are compressed but NOT encrypted
# - .env file is NOT included (contains secrets - store in password manager)
# - Backups stored on same HDD - does NOT protect against HDD failure
# - For disaster recovery: Copy backups to off-site storage periodically
# - For encryption: Use gpg to encrypt backup files after creation
#
# SECRET RECOVERY:
# - Database password: stored in password manager, regenerate if lost
# - Session secret: regenerate and invalidate all sessions
# - Alert webhook token: regenerate and update Alertmanager config

set -euo pipefail

# Configuration
MOUNT_POINT="/mnt/kiboto-storage"
EXPECTED_UUID="85119b59-5917-4243-8041-9e0973ddfbec"
BACKUP_DIR="$MOUNT_POINT/kibolens-data/backups/daily"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7
PROJECT_DIR="/home/sysadmin/kibolens"
COMPOSE_FILE="$PROJECT_DIR/deployment/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env"

# Restrictive umask
umask 077

# Temporary file cleanup on exit
TMP_FILES=()
cleanup() {
    for tmp in "${TMP_FILES[@]}"; do
        rm -f "$tmp" 2>/dev/null || true
    done
}
trap cleanup EXIT INT TERM

# Verify HDD mount and UUID before proceeding
echo "Verifying HDD mount..."
if ! mountpoint -q "$MOUNT_POINT"; then
    echo "ERROR: $MOUNT_POINT is not mounted - refusing to create backup" >&2
    exit 1
fi

MOUNTED_UUID=$(findmnt -n -o UUID "$MOUNT_POINT" 2>/dev/null || echo "")
if [ "$MOUNTED_UUID" != "$EXPECTED_UUID" ]; then
    echo "ERROR: UUID mismatch at $MOUNT_POINT - refusing to create backup" >&2
    echo "  Expected: $EXPECTED_UUID" >&2
    echo "  Got:      $MOUNTED_UUID" >&2
    exit 1
fi

echo "✓ HDD verified (UUID: $EXPECTED_UUID)"

# Ensure backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory does not exist: $BACKUP_DIR" >&2
    exit 1
fi

# PostgreSQL backup to temporary file
echo "Backing up PostgreSQL database..."
TMP_DB_BACKUP="$BACKUP_DIR/.kibolens_db_${DATE}.dump.tmp"
TMP_FILES+=("$TMP_DB_BACKUP")

docker compose \
    --project-directory "$PROJECT_DIR" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    exec -T postgres \
    pg_dump -U kibolens -Fc kibolens \
    > "$TMP_DB_BACKUP"

# Verify backup is not empty
if [ ! -s "$TMP_DB_BACKUP" ]; then
    echo "ERROR: Database backup file is empty" >&2
    exit 1
fi

# Verify backup is valid PostgreSQL custom format
if ! head -c 5 "$TMP_DB_BACKUP" | grep -q "PGDMP"; then
    echo "ERROR: Database backup file is not a valid PostgreSQL dump" >&2
    exit 1
fi

# Verify backup integrity with pg_restore --list
echo "Validating database backup integrity..."
if ! docker compose \
    --project-directory "$PROJECT_DIR" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    exec -T postgres \
    pg_restore --list < "$TMP_DB_BACKUP" > /dev/null 2>&1; then
    echo "ERROR: Database backup validation failed (pg_restore --list)" >&2
    exit 1
fi

# Move to final name only after validation
FINAL_DB_BACKUP="$BACKUP_DIR/kibolens_db_$DATE.dump"
mv "$TMP_DB_BACKUP" "$FINAL_DB_BACKUP"
chmod 600 "$FINAL_DB_BACKUP"
TMP_FILES=("${TMP_FILES[@]/$TMP_DB_BACKUP}")  # Remove from cleanup list
echo "✓ Database backup: $FINAL_DB_BACKUP ($(du -h "$FINAL_DB_BACKUP" | cut -f1))"

# Archive configurations to temporary file
# IMPORTANT: .env is NOT included (contains secrets)
echo "Backing up configuration files..."
TMP_CONFIG_BACKUP="$BACKUP_DIR/.config_${DATE}.tar.gz.tmp"
TMP_FILES+=("$TMP_CONFIG_BACKUP")

# Explicit error handling - fail if tar fails
set +e
tar -czf "$TMP_CONFIG_BACKUP" \
    -C "$PROJECT_DIR" \
    deployment/docker-compose.yml \
    deployment/Caddyfile \
    deployment/systemd/ \
    deployment/scripts/ \
    monitoring/ \
    2>/dev/null
TAR_EXIT=$?
set -e

if [ $TAR_EXIT -ne 0 ]; then
    echo "ERROR: Configuration archive failed (tar exit code: $TAR_EXIT)" >&2
    exit 1
fi

# Verify config archive is not empty
if [ ! -s "$TMP_CONFIG_BACKUP" ]; then
    echo "ERROR: Configuration backup is empty" >&2
    exit 1
fi

# Validate tar archive integrity
echo "Validating configuration archive..."
if ! tar -tzf "$TMP_CONFIG_BACKUP" > /dev/null 2>&1; then
    echo "ERROR: Configuration archive validation failed (tar -tzf)" >&2
    exit 1
fi

FINAL_CONFIG_BACKUP="$BACKUP_DIR/config_$DATE.tar.gz"
mv "$TMP_CONFIG_BACKUP" "$FINAL_CONFIG_BACKUP"
chmod 600 "$FINAL_CONFIG_BACKUP"
TMP_FILES=("${TMP_FILES[@]/$TMP_CONFIG_BACKUP}")  # Remove from cleanup list
echo "✓ Configuration backup: $FINAL_CONFIG_BACKUP ($(du -h "$FINAL_CONFIG_BACKUP" | cut -f1))"

# Cleanup old backups (only after ALL new backups succeeded)
echo "Removing backups older than $RETENTION_DAYS days..."
REMOVED_COUNT=0
REMOVED_COUNT=$((REMOVED_COUNT + $(find "$BACKUP_DIR" -name "kibolens_db_*.dump" -mtime +$RETENTION_DAYS -delete -print | wc -l)))
REMOVED_COUNT=$((REMOVED_COUNT + $(find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)))
echo "✓ Removed $REMOVED_COUNT old backup(s)"

# List current backups
echo ""
echo "Current backups:"
ls -lh "$BACKUP_DIR" | grep -E "kibolens_db_|config_" | tail -5 || echo "  (none)"

# Log success
echo "$(date): Backup completed successfully" >> /var/log/kibolens-backup.log

echo ""
echo "=== Backup Summary ==="
echo "Database: $FINAL_DB_BACKUP"
echo "Config:   $FINAL_CONFIG_BACKUP"
echo "Retention: $RETENTION_DAYS days"
echo "Location: $BACKUP_DIR"
echo ""
echo "IMPORTANT:"
echo "- Backups are on the same HDD and do NOT protect against HDD failure"
echo "- Copy backups to off-site storage for disaster recovery"
echo "- Secrets (.env) are NOT in backups - stored in password manager"
echo "- Backups are compressed but NOT encrypted"

exit 0
