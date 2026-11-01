#!/bin/bash
#
# KiboLens Docker Storage Initialization Script (SSD)
# ONE-TIME SETUP - Creates 40GB logical volume for Docker/containerd on SSD
#
# This script:
# - Verifies LVM state before any modifications
# - Creates /dev/ubuntu-vg/docker-lv (40GB from unallocated space)
# - Formats as ext4
# - Backs up /etc/fstab before changes
# - Adds stable mount entry to /etc/fstab
# - Mounts at /var/lib/docker
# - Creates containerd-root/ subdirectory
# - Leaves ~18.62GB unallocated for future expansion
# - REFUSES to proceed if existing Docker/containerd data would be hidden
# - NEVER automatically formats an existing LV
#
# IMPORTANT: This script MUST be run BEFORE installing Docker/containerd.
# Package installation may auto-start services and initialize data on root FS.
#
# Usage: sudo /home/sysadmin/kibolens/deployment/scripts/kibolens-docker-storage-init.sh

set -euo pipefail

echo "=== KiboLens Docker/containerd Storage Initialization (SSD) ==="
echo ""

# Verify running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root" >&2
    echo "Usage: sudo $0" >&2
    exit 1
fi

# === PRE-CHECK 1: Docker/containerd must not be installed ===
echo "Pre-check 1: Verifying Docker/containerd not yet installed..."
if command -v docker &>/dev/null; then
    echo "ERROR: Docker is already installed" >&2
    echo "  This script must run BEFORE Docker installation" >&2
    echo "  If you need to migrate existing Docker data, stop here and plan migration" >&2
    exit 1
fi

if systemctl list-unit-files 2>/dev/null | grep -q "^containerd.service"; then
    echo "ERROR: containerd service file exists" >&2
    echo "  This script must run BEFORE containerd installation" >&2
    exit 1
fi
echo "   ✓ Docker/containerd not installed"
echo ""

# === PRE-CHECK 2: Existing data that would be hidden ===
echo "Pre-check 2: Checking for existing Docker/containerd data..."
if [ -d "/var/lib/docker" ] && [ "$(ls -A /var/lib/docker 2>/dev/null)" ]; then
    echo "ERROR: /var/lib/docker exists and contains data" >&2
    echo "  Content:" >&2
    ls -la /var/lib/docker | head -10 >&2
    echo "" >&2
    echo "  This data would be hidden by mounting docker-lv at /var/lib/docker" >&2
    echo "  REFUSING to proceed - manual inspection and migration required" >&2
    exit 1
fi

if [ -d "/var/lib/containerd" ] && [ "$(ls -A /var/lib/containerd 2>/dev/null)" ]; then
    echo "ERROR: /var/lib/containerd exists and contains data" >&2
    echo "  Content:" >&2
    ls -la /var/lib/containerd | head -10 >&2
    echo "" >&2
    echo "  After SSD setup, containerd will use /var/lib/docker/containerd-root" >&2
    echo "  Existing data at /var/lib/containerd must be migrated manually" >&2
    echo "  REFUSING to proceed - manual data migration required" >&2
    exit 1
fi
echo "   ✓ No existing Docker/containerd data found"
echo ""

# Check if docker-lv already exists
echo "1. Checking for existing docker-lv..."
if lvdisplay ubuntu-vg/docker-lv &>/dev/null; then
    echo "   ✓ docker-lv already exists - verifying configuration"
    echo ""
    
    # Verify LV size
    LV_SIZE=$(lvdisplay ubuntu-vg/docker-lv | grep "LV Size" | awk '{print $3, $4}')
    echo "   LV Size: $LV_SIZE"
    
    # Check if size is approximately 40GB (allow some tolerance)
    LV_SIZE_GB=$(lvdisplay ubuntu-vg/docker-lv --units g | grep "LV Size" | awk '{print $3}' | sed 's/g//' | sed 's/\..*//')
    if [ "$LV_SIZE_GB" -lt 38 ] || [ "$LV_SIZE_GB" -gt 42 ]; then
        echo "ERROR: docker-lv size mismatch" >&2
        echo "  Expected: ~40GB" >&2
        echo "  Found: ${LV_SIZE_GB}GB" >&2
        exit 1
    fi
    
    # Verify filesystem type
    FS_TYPE=$(blkid /dev/ubuntu-vg/docker-lv -o value -s TYPE 2>/dev/null || echo "none")
    echo "   Filesystem: $FS_TYPE"
    
    if [ "$FS_TYPE" != "ext4" ]; then
        echo "ERROR: Unexpected filesystem type on docker-lv" >&2
        echo "  Expected: ext4" >&2
        echo "  Found: $FS_TYPE" >&2
        echo "" >&2
        echo "  Refusing to auto-format existing LV with filesystem: $FS_TYPE" >&2
        exit 1
    fi
    
    # Check fstab entry
    echo "   Checking /etc/fstab..."
    if grep -q "docker-lv.*docker" /etc/fstab; then
        echo "   ✓ fstab entry exists"
        grep "docker-lv" /etc/fstab
    else
        echo "ERROR: docker-lv exists but no fstab entry found" >&2
        echo "  Add to /etc/fstab:" >&2
        echo "  /dev/ubuntu-vg/docker-lv /var/lib/docker ext4 defaults 0 2" >&2
        exit 1
    fi
    
    # Check if mounted
    echo ""
    if mountpoint -q /var/lib/docker; then
        MOUNT_SRC=$(findmnt -n -o SOURCE /var/lib/docker)
        if [ "$MOUNT_SRC" = "/dev/mapper/ubuntu--vg-docker--lv" ]; then
            echo "   ✓ /var/lib/docker is mounted from docker-lv"
            df -h /var/lib/docker
            echo ""
            
            # Check containerd-root directory
            if [ -d "/var/lib/docker/containerd-root" ]; then
                echo "   ✓ containerd-root directory exists"
            else
                echo "   ⚠ Creating containerd-root directory..."
                mkdir -p /var/lib/docker/containerd-root
                echo "   ✓ Created /var/lib/docker/containerd-root"
            fi
            
            echo ""
            echo "=== docker-lv is correctly configured ==="
            echo "No further action needed"
        else
            echo "ERROR: /var/lib/docker is mounted but not from docker-lv" >&2
            echo "  Expected source: /dev/mapper/ubuntu--vg-docker--lv" >&2
            echo "  Found source: $MOUNT_SRC" >&2
            exit 1
        fi
    else
        echo "ERROR: docker-lv exists but /var/lib/docker not mounted" >&2
        echo "  Run: sudo mount /var/lib/docker" >&2
        echo "  Or reload systemd: sudo systemctl daemon-reload && sudo systemctl start var-lib-docker.mount" >&2
        exit 1
    fi
    exit 0
fi

echo "   docker-lv does not exist - will create new volume"
echo ""

# Verify volume group exists
echo "2. Verifying ubuntu-vg volume group..."
if ! vgdisplay ubuntu-vg &>/dev/null; then
    echo "ERROR: Volume group ubuntu-vg not found" >&2
    echo "  Run: sudo vgdisplay" >&2
    exit 1
fi

VG_SIZE=$(vgdisplay ubuntu-vg | grep "VG Size" | awk '{print $3, $4}')
echo "   ✓ ubuntu-vg found (Size: $VG_SIZE)"

# Verify expected root LV exists and is unchanged
echo "3. Verifying existing root logical volume..."
if ! lvdisplay ubuntu-vg/ubuntu-lv &>/dev/null; then
    echo "ERROR: Expected root LV ubuntu-vg/ubuntu-lv not found" >&2
    echo "  This script expects a standard Ubuntu LVM layout" >&2
    exit 1
fi

ROOT_LV_SIZE=$(lvdisplay ubuntu-vg/ubuntu-lv --units g | grep "LV Size" | awk '{print $3}' | sed 's/g//' | sed 's/\..*//')
echo "   ✓ ubuntu-lv exists (Size: ~${ROOT_LV_SIZE}GB)"

# Expected root LV size: 58.62GB
if [ "$ROOT_LV_SIZE" -lt 55 ] || [ "$ROOT_LV_SIZE" -gt 62 ]; then
    echo "WARNING: Root LV size differs from expected 58.62GB" >&2
    echo "  Expected: ~59GB" >&2
    echo "  Found: ${ROOT_LV_SIZE}GB" >&2
    read -p "Continue anyway? (yes/no): " CONFIRM_SIZE
    if [ "$CONFIRM_SIZE" != "yes" ]; then
        echo "Aborted by user"
        exit 1
    fi
fi

# Check free space in volume group
echo "4. Checking available space..."
VG_FREE_MB=$(vgdisplay ubuntu-vg --units m | grep "Free" | awk '{print $7}' | sed 's/<//g' | sed 's/m//g' | cut -d. -f1)
VG_FREE_GB=$((VG_FREE_MB / 1024))

echo "   Free space in ubuntu-vg: ${VG_FREE_GB}GB"

if [ "$VG_FREE_GB" -lt 40 ]; then
    echo "ERROR: Insufficient free space in ubuntu-vg" >&2
    echo "  Need: 40GB" >&2
    echo "  Have: ${VG_FREE_GB}GB" >&2
    echo "" >&2
    echo "  Current LVM layout:" >&2
    lvs ubuntu-vg >&2
    exit 1
fi

REMAINING_GB=$((VG_FREE_GB - 40))
echo "   ✓ Sufficient space available"
echo "   After creation: ~${REMAINING_GB}GB will remain unallocated"
echo ""

# Check if /var/lib/docker is already mounted elsewhere
echo "5. Checking /var/lib/docker mount status..."
if mountpoint -q /var/lib/docker 2>/dev/null; then
    CURRENT_SOURCE=$(findmnt -n -o SOURCE /var/lib/docker)
    echo "ERROR: /var/lib/docker is already mounted" >&2
    echo "  Source: $CURRENT_SOURCE" >&2
    echo "  Unmount first: sudo umount /var/lib/docker" >&2
    exit 1
fi
echo "   ✓ /var/lib/docker is not currently mounted"
echo ""

# Summary and confirmation
echo "=== Pre-creation Summary ==="
echo "Volume Group: ubuntu-vg"
echo "  Total Size: $VG_SIZE"
echo "  Free Space: ${VG_FREE_GB}GB"
echo "  Root LV: ubuntu-lv (~${ROOT_LV_SIZE}GB)"
echo ""
echo "Will create:"
echo "  Logical Volume: /dev/ubuntu-vg/docker-lv (40GB)"
echo "  Filesystem: ext4 with label 'kibolens-docker'"
echo "  Mount Point: /var/lib/docker"
echo "  fstab entry: /dev/ubuntu-vg/docker-lv /var/lib/docker ext4 defaults 0 2"
echo "  Subdirectories:"
echo "    /var/lib/docker/containerd-root/  (for containerd data)"
echo ""
echo "After creation:"
echo "  Unallocated space: ~${REMAINING_GB}GB (reserved for future expansion)"
echo ""
read -p "Proceed with LV creation? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted by user"
    exit 1
fi

# Create logical volume
echo ""
echo "6. Creating logical volume..."
if ! lvcreate -L 40G -n docker-lv ubuntu-vg; then
    echo "ERROR: Failed to create logical volume" >&2
    exit 1
fi
echo "   ✓ Logical volume created: /dev/ubuntu-vg/docker-lv"

# Create ext4 filesystem with label
echo "7. Creating ext4 filesystem..."
if ! mkfs.ext4 -L kibolens-docker /dev/ubuntu-vg/docker-lv; then
    echo "ERROR: Failed to create filesystem" >&2
    echo "  Cleanup: sudo lvremove -f ubuntu-vg/docker-lv" >&2
    exit 1
fi
echo "   ✓ Filesystem created with label 'kibolens-docker'"

# Create mount point
echo "8. Creating mount point..."
if [ ! -d /var/lib/docker ]; then
    mkdir -p /var/lib/docker
    echo "   ✓ Created /var/lib/docker"
else
    echo "   ✓ /var/lib/docker exists"
fi

# Backup fstab
echo "9. Backing up /etc/fstab..."
FSTAB_BACKUP="/etc/fstab.backup.$(date +%Y%m%d_%H%M%S)"
cp /etc/fstab "$FSTAB_BACKUP"
echo "   ✓ Backup created: $FSTAB_BACKUP"

# Check for conflicting entries
echo "10. Checking for conflicting fstab entries..."
if grep -q "^[^#].*[[:space:]]/var/lib/docker[[:space:]]" /etc/fstab; then
    echo "ERROR: Conflicting mount entry found in /etc/fstab" >&2
    grep "/var/lib/docker" /etc/fstab >&2
    echo "" >&2
    echo "  Remove conflicting entry and rerun this script" >&2
    echo "  fstab backup: $FSTAB_BACKUP" >&2
    exit 1
fi
echo "   ✓ No conflicts found"

# Add to fstab
echo "11. Adding mount entry to /etc/fstab..."
FSTAB_ENTRY="/dev/ubuntu-vg/docker-lv /var/lib/docker ext4 defaults 0 2"

if grep -q "docker-lv" /etc/fstab; then
    echo "   ⚠ Entry containing 'docker-lv' already exists"
    grep "docker-lv" /etc/fstab
else
    echo "$FSTAB_ENTRY" >> /etc/fstab
    echo "   ✓ Added: $FSTAB_ENTRY"
fi

# Reload systemd
echo "12. Reloading systemd..."
systemctl daemon-reload
echo "   ✓ Systemd reloaded"

# Verify systemd mount unit
echo "13. Verifying systemd mount unit..."
if systemctl list-unit-files | grep -q "var-lib-docker.mount"; then
    echo "   ✓ var-lib-docker.mount unit generated"
else
    echo "   ⚠ WARNING: var-lib-docker.mount unit not found" >&2
    echo "   Mount unit may be generated on next boot" >&2
fi

# Mount the filesystem
echo "14. Mounting /var/lib/docker..."
if ! mount /var/lib/docker; then
    echo "ERROR: Failed to mount /var/lib/docker" >&2
    echo "  Check: mount | grep docker" >&2
    echo "  Manual mount: sudo mount -t ext4 /dev/ubuntu-vg/docker-lv /var/lib/docker" >&2
    exit 1
fi
echo "   ✓ Mounted successfully"

# Create containerd-root directory
echo "15. Creating containerd-root directory..."
mkdir -p /var/lib/docker/containerd-root
echo "   ✓ Created /var/lib/docker/containerd-root"

# Verify mount
echo ""
echo "=== Final Verification ==="
echo "Mount point:"
df -h /var/lib/docker
echo ""
echo "Logical volume:"
lvdisplay ubuntu-vg/docker-lv | grep -E "LV Name|LV Size|LV Path|LV Status"
echo ""
echo "Filesystem:"
blkid /dev/ubuntu-vg/docker-lv
echo ""
echo "Directories:"
ls -la /var/lib/docker
echo ""

# Show remaining VG capacity
VG_FREE_AFTER_MB=$(vgdisplay ubuntu-vg --units m | grep "Free" | awk '{print $7}' | sed 's/<//g' | sed 's/m//g' | cut -d. -f1)
VG_FREE_AFTER_GB=$((VG_FREE_AFTER_MB / 1024))
echo "Remaining unallocated capacity in ubuntu-vg: ${VG_FREE_AFTER_GB}GB"

echo ""
echo "=== Docker/containerd Storage Initialization Complete ==="
echo ""
echo "Summary:"
echo "  ✓ Logical Volume: /dev/ubuntu-vg/docker-lv (40GB)"
echo "  ✓ Filesystem: ext4 (label: kibolens-docker)"
echo "  ✓ Mount Point: /var/lib/docker"
echo "  ✓ containerd root: /var/lib/docker/containerd-root/"
echo "  ✓ fstab entry added (backup: $FSTAB_BACKUP)"
echo "  ✓ Systemd mount unit: var-lib-docker.mount"
echo "  ✓ Current mount verified"
echo "  ℹ Unallocated VG space: ~${VG_FREE_AFTER_GB}GB"
echo ""
echo "Next steps:"
echo "1. Reboot to verify auto-mount:"
echo "     sudo reboot"
echo "     # After reboot:"
echo "     mountpoint /var/lib/docker"
echo "     df -h /var/lib/docker"
echo ""
echo "2. Install systemd drop-ins BEFORE installing Docker:"
echo "     sudo mkdir -p /etc/systemd/system/docker.service.d/"
echo "     sudo mkdir -p /etc/systemd/system/containerd.service.d/"
echo "     sudo cp ~/kibolens/deployment/systemd/docker.service.d/kibolens-storage.conf \\"
echo "       /etc/systemd/system/docker.service.d/"
echo "     sudo cp ~/kibolens/deployment/systemd/containerd.service.d/kibolens-storage.conf \\"
echo "       /etc/systemd/system/containerd.service.d/"
echo "     sudo systemctl daemon-reload"
echo ""
echo "3. Install Docker and containerd:"
echo "     curl -fsSL https://get.docker.com | sh"
echo ""
echo "4. Configure containerd root (AFTER installation):"
echo "     sudo mkdir -p /etc/containerd"
echo "     sudo containerd config default > /tmp/containerd-config.toml"
echo "     # Edit /tmp/containerd-config.toml:"
echo "     #   Change: root = \"/var/lib/containerd\""
echo "     #   To:     root = \"/var/lib/docker/containerd-root\""
echo "     sudo cp /tmp/containerd-config.toml /etc/containerd/config.toml"
echo "     sudo systemctl restart containerd"
echo "     sudo systemctl restart docker"
echo ""
echo "5. Verify both services are using SSD storage:"
echo "     systemctl status containerd"
echo "     systemctl status docker"
echo "     docker info | grep 'Docker Root Dir'"
echo ""
echo "Recovery (if needed):"
echo "  - fstab backup: $FSTAB_BACKUP"
echo "  - Unmount: sudo umount /var/lib/docker"
echo "  - Remove LV: sudo lvremove ubuntu-vg/docker-lv"
echo "  - Restore fstab: sudo cp $FSTAB_BACKUP /etc/fstab"

exit 0
