#!/bin/bash
#
# KiboLens HDD Storage Initialization Script
# ONE-TIME SETUP - Creates KiboLens data directories on HDD
#
# This script:
# - Verifies the HDD is mounted with correct UUID
# - Creates KiboLens data directories on HDD
# - Sets ownership for container UIDs
# - Does NOT modify existing user directories
# - Does NOT create PostgreSQL/Prometheus directories (now Docker volumes on SSD)
#
# Usage: sudo /home/sysadmin/kibolens/deployment/scripts/kibolens-storage-init.sh

set -euo pipefail

MOUNT_POINT="/mnt/kiboto-storage"
EXPECTED_UUID="85119b59-5917-4243-8041-9e0973ddfbec"
DATA_DIR="$MOUNT_POINT/kibolens-data"

echo "=== KiboLens HDD Storage Initialization ==="
echo ""

# Verify running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root" >&2
    echo "Usage: sudo $0" >&2
    exit 1
fi

# Check if mounted
echo "1. Verifying HDD mount..."
if ! mountpoint -q "$MOUNT_POINT"; then
    echo "ERROR: $MOUNT_POINT is not mounted" >&2
    exit 1
fi
echo "   ✓ $MOUNT_POINT is a mount point"

# Verify UUID
echo "2. Verifying UUID..."
MOUNTED_UUID=$(findmnt -n -o UUID "$MOUNT_POINT" 2>/dev/null || echo "")
if [ -z "$MOUNTED_UUID" ]; then
    echo "ERROR: Could not determine UUID of $MOUNT_POINT" >&2
    exit 1
fi

if [ "$MOUNTED_UUID" != "$EXPECTED_UUID" ]; then
    echo "ERROR: UUID mismatch at $MOUNT_POINT" >&2
    echo "  Expected: $EXPECTED_UUID" >&2
    echo "  Got:      $MOUNTED_UUID" >&2
    exit 1
fi
echo "   ✓ UUID matches: $EXPECTED_UUID"

# Verify writable
echo "3. Verifying write access..."
if [ ! -w "$MOUNT_POINT" ]; then
    echo "ERROR: $MOUNT_POINT is not writable" >&2
    exit 1
fi
echo "   ✓ Mount point is writable"

# Check existing directories
echo "4. Checking existing directory structure..."
echo "   Existing directories in $MOUNT_POINT:"
ls -1 "$MOUNT_POINT" 2>/dev/null || echo "   (empty)"

# Create KiboLens directory structure
echo "5. Creating KiboLens directory structure..."
if [ -d "$DATA_DIR" ]; then
    echo "   ⚠ Warning: $DATA_DIR already exists"
    echo "   Existing contents will be preserved, only missing directories created"
fi

# HDD directories: documents (RAG), backups, secrets, grafana, alertmanager
# NOTE: PostgreSQL and Prometheus now use Docker volumes on SSD (not created here)
mkdir -p "$DATA_DIR"/{documents,backups,secrets,grafana,alertmanager}
mkdir -p "$DATA_DIR/backups"/{daily,manual}
echo "   ✓ Directory structure created"

# Set ownership and permissions
echo "6. Configuring ownership and permissions..."

# Documents: Original files for RAG ingestion (owned by sysadmin)
echo "   - Documents: UID 1000:1000, mode 0755"
if [ ! -d "$DATA_DIR/documents" ]; then
    mkdir -p "$DATA_DIR/documents"
fi
chown 1000:1000 "$DATA_DIR/documents"
chmod 0755 "$DATA_DIR/documents"

# Check if documents contains existing data
DOC_COUNT=$(find "$DATA_DIR/documents" -mindepth 1 2>/dev/null | wc -l)
if [ "$DOC_COUNT" -gt 0 ]; then
    echo "   ℹ Documents directory contains $DOC_COUNT existing items (preserved)"
    # Verify ownership
    DOC_OWNER=$(stat -c "%u:%g" "$DATA_DIR/documents" 2>/dev/null || echo "")
    if [ "$DOC_OWNER" != "1000:1000" ]; then
        echo "   ⚠ WARNING: Unexpected ownership on documents: $DOC_OWNER" >&2
        echo "   Expected: 1000:1000 (sysadmin:sysadmin)" >&2
        echo "   NOT changing ownership - manual review required" >&2
    fi
fi

# Backups: Owned by sysadmin (restrictive)
echo "   - Backups: UID 1000:1000, mode 0700"
mkdir -p "$DATA_DIR/backups"/{daily,manual}
chown 1000:1000 "$DATA_DIR/backups"
chown 1000:1000 "$DATA_DIR/backups"/daily
chown 1000:1000 "$DATA_DIR/backups"/manual
chmod 0700 "$DATA_DIR/backups"
chmod 0700 "$DATA_DIR/backups"/daily
chmod 0700 "$DATA_DIR/backups"/manual

# Check if backups contains existing data
BACKUP_COUNT=$(find "$DATA_DIR/backups" -mindepth 1 -type f 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 0 ]; then
    echo "   ℹ Backups directory contains $BACKUP_COUNT existing files (preserved)"
fi

# Secrets: Token file readable by Alertmanager (GID 65534)
echo "   - Secrets: Token file for Alertmanager (UID 1000:65534)"
chown 1000:65534 "$DATA_DIR/secrets"
chmod 0750 "$DATA_DIR/secrets"

# Grafana: Container runs as UID 472 (grafana user)
echo "   - Grafana dashboards: UID 472:472, mode 0755"
if [ ! -d "$DATA_DIR/grafana" ]; then
    mkdir -p "$DATA_DIR/grafana"
fi
chown 472:472 "$DATA_DIR/grafana"
chmod 0755 "$DATA_DIR/grafana"

# Alertmanager: Container runs as UID 65534 (nobody user)
echo "   - Alertmanager state: UID 65534:65534, mode 0755"
if [ ! -d "$DATA_DIR/alertmanager" ]; then
    mkdir -p "$DATA_DIR/alertmanager"
fi
chown 65534:65534 "$DATA_DIR/alertmanager"
chmod 0755 "$DATA_DIR/alertmanager"

echo "   ✓ Ownership and permissions configured"

# Note about PostgreSQL and Prometheus
echo "7. Storage architecture notes..."
echo "   ℹ PostgreSQL and Prometheus now use Docker volumes on SSD (/var/lib/docker)"
echo "   ℹ These directories are NOT created on the HDD"
echo "   ℹ Docker volumes provide better I/O performance for active data"

# Summary
echo ""
echo "=== HDD Storage Initialization Complete ==="
echo ""
echo "Directory structure:"
ls -la "$DATA_DIR"
echo ""
echo "Storage architecture:"
echo "  SSD (/var/lib/docker):"
echo "    - PostgreSQL database (Docker volume)"
echo "    - Prometheus TSDB (Docker volume)"
echo "    - pgvector embeddings (in PostgreSQL)"
echo ""
echo "  HDD (/mnt/kiboto-storage/kibolens-data/):"
echo "    - documents/     (RAG original files)"
echo "    - backups/       (database and config backups)"
echo "    - secrets/       (alert tokens)"
echo "    - grafana/       (dashboards - optional monitoring)"
echo "    - alertmanager/  (alert state - optional monitoring)"
echo ""
echo "Next steps:"
echo "1. Create alert token file (use same value in .env):"
echo "     TOKEN=\$(openssl rand -hex 32)"
echo "     echo -n \"\$TOKEN\" | sudo tee $DATA_DIR/secrets/kibolens-alert-token >/dev/null"
echo "     sudo chmod 640 $DATA_DIR/secrets/kibolens-alert-token"
echo "     sudo chown 1000:65534 $DATA_DIR/secrets/kibolens-alert-token"
echo "   (Owner sysadmin can read/write, group 65534 [Alertmanager] can read)"
echo ""
echo "2. Create .env file at /home/sysadmin/kibolens/.env:"
echo "     cd /home/sysadmin/kibolens"
echo "     cp .env.example .env"
echo "     chmod 600 .env"
echo "   Edit .env and set (using same TOKEN from step 1):"
echo "     KIBOLENS_ENVIRONMENT=production"
echo "     KIBOLENS_SESSION_COOKIE_SECURE=true"
echo "     KIBOLENS_ALERT_WEBHOOK_TOKEN=\$TOKEN"
echo "   Generate other secrets:"
echo "     KIBOLENS_SESSION_HASH_SECRET=\$(openssl rand -hex 32)"
echo "     POSTGRES_PASSWORD=\$(openssl rand -hex 24)"
echo "   Update .env with all secret values"
echo ""
echo "3. Verify Docker storage initialized:"
echo "     mountpoint /var/lib/docker"
echo "     df -h /var/lib/docker"
echo "     ls -la /var/lib/docker/containerd-root"
echo ""
echo "4. Start KiboLens: sudo systemctl start kibolens.service"
echo ""
echo "Existing user directories (appdata, media, users, etc.) were NOT modified."

exit 0
