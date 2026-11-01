#!/bin/bash
#
# KiboLens Dual-Mount Verification Script
# RECURRING CHECK - Runs before every KiboLens service start
#
# This script:
# - Verifies /var/lib/docker is mounted (SSD Docker volume)
# - Verifies /mnt/kiboto-storage is mounted with correct UUID (HDD)
# - Verifies required KiboLens directories exist on HDD
# - Does NOT create directories
# - Does NOT change ownership or permissions
#
# Exits with code 1 if any check fails, preventing KiboLens from starting

set -euo pipefail

DOCKER_MOUNT="/var/lib/docker"
HDD_MOUNT="/mnt/kiboto-storage"
EXPECTED_UUID="85119b59-5917-4243-8041-9e0973ddfbec"
DATA_DIR="$HDD_MOUNT/kibolens-data"

echo "=== KiboLens Dual-Mount Verification ==="
echo ""

# Check Docker volume (SSD)
echo "1. Verifying Docker storage (SSD)..."
if ! mountpoint -q "$DOCKER_MOUNT"; then
    echo "ERROR: $DOCKER_MOUNT is not mounted" >&2
    echo "  Docker storage volume must be mounted before KiboLens can start" >&2
    echo "  Run: sudo mount $DOCKER_MOUNT" >&2
    echo "  Or create volume: sudo /home/sysadmin/kibolens/deployment/scripts/kibolens-docker-storage-init.sh" >&2
    exit 1
fi

# Verify Docker mount is on correct logical volume (fail-closed)
DOCKER_DEV=$(findmnt -n -o SOURCE "$DOCKER_MOUNT" 2>/dev/null || echo "")
if [ "$DOCKER_DEV" != "/dev/mapper/ubuntu--vg-docker--lv" ]; then
    echo "ERROR: $DOCKER_MOUNT not on expected LV" >&2
    echo "  Expected: /dev/mapper/ubuntu--vg-docker--lv" >&2
    echo "  Got: $DOCKER_DEV" >&2
    echo "  Wrong storage device - refusing to start" >&2
    exit 1
fi

# Verify Docker mount filesystem type
DOCKER_FSTYPE=$(findmnt -n -o FSTYPE "$DOCKER_MOUNT" 2>/dev/null || echo "")
if [ "$DOCKER_FSTYPE" != "ext4" ]; then
    echo "ERROR: $DOCKER_MOUNT has wrong filesystem type" >&2
    echo "  Expected: ext4" >&2
    echo "  Got: $DOCKER_FSTYPE" >&2
    echo "  Wrong filesystem - refusing to start" >&2
    exit 1
fi

echo "   ✓ Docker storage mounted at $DOCKER_MOUNT"
echo "   Device: $DOCKER_DEV"
echo "   Filesystem: $DOCKER_FSTYPE"
echo ""

# Check HDD mount
echo "2. Verifying HDD storage..."
if ! mountpoint -q "$HDD_MOUNT"; then
    echo "ERROR: $HDD_MOUNT is not mounted" >&2
    echo "  HDD must be mounted before KiboLens can start" >&2
    exit 1
fi

# Verify UUID matches expected device
MOUNTED_UUID=$(findmnt -n -o UUID "$HDD_MOUNT" 2>/dev/null || echo "")
if [ -z "$MOUNTED_UUID" ]; then
    echo "ERROR: Could not determine UUID of $HDD_MOUNT" >&2
    exit 1
fi

if [ "$MOUNTED_UUID" != "$EXPECTED_UUID" ]; then
    echo "ERROR: UUID mismatch at $HDD_MOUNT" >&2
    echo "  Expected: $EXPECTED_UUID" >&2
    echo "  Got:      $MOUNTED_UUID" >&2
    echo "  Wrong disk mounted - refusing to start" >&2
    exit 1
fi

echo "   ✓ HDD storage mounted at $HDD_MOUNT (UUID: $MOUNTED_UUID)"
echo ""

# Verify required HDD directories exist
echo "3. Verifying required directories on HDD..."
REQUIRED_DIRS=(
    "$DATA_DIR"
    "$DATA_DIR/documents"
    "$DATA_DIR/backups"
    "$DATA_DIR/secrets"
)

MISSING=0
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        echo "ERROR: Required directory missing: $dir" >&2
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo "" >&2
    echo "Run storage initialization script first:" >&2
    echo "  sudo /home/sysadmin/kibolens/deployment/scripts/kibolens-storage-init.sh" >&2
    exit 1
fi

echo "   ✓ All required HDD directories exist"
echo ""

# Optional monitoring directories (only warn if missing)
MONITORING_DIRS=(
    "$DATA_DIR/grafana"
    "$DATA_DIR/alertmanager"
)

MONITORING_MISSING=0
for dir in "${MONITORING_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        MONITORING_MISSING=1
    fi
done

if [ "$MONITORING_MISSING" -eq 1 ]; then
    echo "⚠ Warning: Monitoring directories incomplete" >&2
    echo "  Monitoring profile will fail if enabled" >&2
    echo "  Run storage initialization to create all directories" >&2
    echo ""
fi

# Show storage status
echo "=== Storage Status ==="
echo "SSD (Docker + containerd):"
df -h "$DOCKER_MOUNT" | tail -1
echo ""
echo "HDD (Application Data):"
df -h "$HDD_MOUNT" | tail -1
echo ""

# Success - all critical checks passed
echo "✓ Dual-mount verification complete"
echo "  SSD: $DOCKER_MOUNT (Docker + containerd on docker-lv)"
echo "  HDD: $HDD_MOUNT (backups, documents, secrets)"
exit 0
