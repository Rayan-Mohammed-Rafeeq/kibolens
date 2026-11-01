#!/bin/bash
#
# KiboLens Monitoring Profile Management
#
# Usage:
#   sudo /home/sysadmin/kibolens/deployment/scripts/kibolens-monitoring.sh [enable|disable|status]
#
# This script manages the optional monitoring profile (Prometheus, Grafana, etc.)
# independently of the core KiboLens services managed by systemd.

set -euo pipefail

PROJECT_DIR="/home/sysadmin/kibolens"
COMPOSE_FILE="$PROJECT_DIR/deployment/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env"
MOUNT_CHECK_SCRIPT="/usr/local/bin/kibolens-mount-check.sh"

ACTION="${1:-status}"

# Verify running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root" >&2
    echo "Usage: sudo $0 [enable|disable|status]" >&2
    exit 1
fi

case "$ACTION" in
    enable)
        echo "Enabling KiboLens monitoring profile..."
        echo ""
        
        # Run mount verification
        echo "1. Verifying HDD mount..."
        if ! "$MOUNT_CHECK_SCRIPT"; then
            echo "ERROR: Mount verification failed" >&2
            exit 1
        fi
        echo ""
        
        # Verify monitoring data directories exist on HDD
        # Note: Prometheus uses Docker named volume on SSD, not HDD
        echo "2. Verifying monitoring directories on HDD..."
        REQUIRED_DIRS=(
            "/mnt/kiboto-storage/kibolens-data/alertmanager"
            "/mnt/kiboto-storage/kibolens-data/grafana"
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
            echo "  sudo $PROJECT_DIR/deployment/scripts/kibolens-storage-init.sh" >&2
            exit 1
        fi
        echo "   ✓ Monitoring directories exist on HDD (Alertmanager, Grafana)"
        echo "   Note: Prometheus TSDB uses Docker volume on SSD"
        echo ""
        
        # Verify Alertmanager token file with strict validation
        echo "3. Verifying Alertmanager token file..."
        TOKEN_FILE="/mnt/kiboto-storage/kibolens-data/secrets/kibolens-alert-token"
        
        # Check 1: File exists
        if [ ! -f "$TOKEN_FILE" ]; then
            echo "ERROR: Alert token file missing: $TOKEN_FILE" >&2
            echo "" >&2
            echo "Create token file (use same value in .env):" >&2
            echo "  TOKEN=\$(openssl rand -hex 32)" >&2
            echo "  echo -n \"\$TOKEN\" | sudo tee $TOKEN_FILE >/dev/null" >&2
            echo "  sudo chmod 640 $TOKEN_FILE" >&2
            echo "  sudo chown 1000:65534 $TOKEN_FILE" >&2
            echo "" >&2
            echo "Add same token to .env:" >&2
            echo "  KIBOLENS_ALERT_WEBHOOK_TOKEN=\$TOKEN" >&2
            exit 1
        fi
        
        # Check 2: Regular file (not symlink)
        if [ -L "$TOKEN_FILE" ]; then
            echo "ERROR: Token file is a symlink: $TOKEN_FILE" >&2
            echo "  Token file must be a regular file, not a symlink" >&2
            exit 1
        fi
        
        # Check 3: Non-empty
        if [ ! -s "$TOKEN_FILE" ]; then
            echo "ERROR: Token file is empty: $TOKEN_FILE" >&2
            echo "  Token file must contain the webhook token" >&2
            exit 1
        fi
        
        # Check 4: UID must be 1000
        TOKEN_UID=$(stat -c "%u" "$TOKEN_FILE" 2>/dev/null || echo "")
        if [ "$TOKEN_UID" != "1000" ]; then
            echo "ERROR: Token file UID is $TOKEN_UID, expected 1000 (sysadmin)" >&2
            echo "  Fix with: sudo chown 1000:65534 $TOKEN_FILE" >&2
            exit 1
        fi
        
        # Check 5: GID must be 65534 (Alertmanager)
        TOKEN_GID=$(stat -c "%g" "$TOKEN_FILE" 2>/dev/null || echo "")
        if [ "$TOKEN_GID" != "65534" ]; then
            echo "ERROR: Token file GID is $TOKEN_GID, expected 65534 (Alertmanager)" >&2
            echo "  Fix with: sudo chown 1000:65534 $TOKEN_FILE" >&2
            exit 1
        fi
        
        # Check 6: Mode must be exactly 640
        TOKEN_MODE=$(stat -c "%a" "$TOKEN_FILE" 2>/dev/null || echo "000")
        if [ "$TOKEN_MODE" != "640" ]; then
            echo "ERROR: Token file mode is $TOKEN_MODE, expected 640" >&2
            echo "  Owner (sysadmin) must have read/write, group (Alertmanager) must have read" >&2
            echo "  Fix with: sudo chmod 640 $TOKEN_FILE" >&2
            exit 1
        fi
        
        echo "   ✓ Token file verified: $TOKEN_FILE"
        echo "   UID: 1000, GID: 65534, Mode: 640"
        echo ""
        
        # Start monitoring profile
        echo "4. Starting monitoring services..."
        docker compose \
            --project-directory "$PROJECT_DIR" \
            --env-file "$ENV_FILE" \
            -f "$COMPOSE_FILE" \
            --profile monitoring \
            up -d
        
        echo ""
        echo "✓ Monitoring profile enabled"
        echo ""
        echo "Services started:"
        docker compose \
            --project-directory "$PROJECT_DIR" \
            --env-file "$ENV_FILE" \
            -f "$COMPOSE_FILE" \
            ps prometheus node-exporter cadvisor alertmanager grafana
        ;;
        
    disable)
        echo "Disabling KiboLens monitoring profile..."
        echo ""
        
        # Stop only monitoring profile containers
        docker compose \
            --project-directory "$PROJECT_DIR" \
            --env-file "$ENV_FILE" \
            -f "$COMPOSE_FILE" \
            stop prometheus grafana alertmanager node-exporter cadvisor 2>/dev/null || true
        
        # Remove monitoring containers (preserves data volumes)
        docker compose \
            --project-directory "$PROJECT_DIR" \
            --env-file "$ENV_FILE" \
            -f "$COMPOSE_FILE" \
            rm -f prometheus grafana alertmanager node-exporter cadvisor 2>/dev/null || true
        
        echo "✓ Monitoring profile disabled"
        echo "  Core services remain running"
        echo "  Monitoring data preserved in /mnt/kiboto-storage/kibolens-data/"
        ;;
        
    status)
        echo "KiboLens Monitoring Profile Status:"
        echo ""
        
        # Check each monitoring service individually
        SERVICES=("prometheus" "node-exporter" "cadvisor" "alertmanager" "grafana")
        RUNNING=0
        STOPPED=0
        OTHER=0
        
        for service in "${SERVICES[@]}"; do
            # docker compose ps returns JSON Lines (one JSON object per line)
            # Use head -1 to get first line, then parse with jq
            # STATE can be: running, restarting, removing, paused, exited, dead, created
            STATE=$(docker compose \
                --project-directory "$PROJECT_DIR" \
                --env-file "$ENV_FILE" \
                -f "$COMPOSE_FILE" \
                ps "$service" --format json 2>/dev/null | head -1 | jq -r '.State' 2>/dev/null || echo "not-created")
            
            case "$STATE" in
                running)
                    echo "  ✓ $service: running"
                    RUNNING=$((RUNNING + 1))
                    ;;
                exited)
                    echo "  ✗ $service: stopped"
                    STOPPED=$((STOPPED + 1))
                    ;;
                restarting)
                    echo "  ⟳ $service: restarting"
                    OTHER=$((OTHER + 1))
                    ;;
                paused)
                    echo "  ‖ $service: paused"
                    OTHER=$((OTHER + 1))
                    ;;
                dead|removing)
                    echo "  ✗ $service: $STATE"
                    OTHER=$((OTHER + 1))
                    ;;
                not-created|"")
                    echo "  - $service: not created"
                    ;;
                *)
                    echo "  ? $service: unknown state ($STATE)"
                    OTHER=$((OTHER + 1))
                    ;;
            esac
        done
        
        TOTAL=$((RUNNING + STOPPED + OTHER))
        echo ""
        if [ "$RUNNING" -eq 5 ]; then
            echo "Status: ENABLED (all monitoring services running)"
        elif [ "$RUNNING" -gt 0 ]; then
            echo "Status: PARTIAL ($RUNNING/$TOTAL services running, $STOPPED stopped, $OTHER other)"
        elif [ "$TOTAL" -gt 0 ]; then
            echo "Status: STOPPED ($STOPPED stopped, $OTHER other states)"
            echo ""
            echo "To enable: sudo $0 enable"
        else
            echo "Status: DISABLED (no monitoring services created)"
            echo ""
            echo "To enable: sudo $0 enable"
        fi
        ;;
        
    *)
        echo "Usage: $0 [enable|disable|status]" >&2
        exit 1
        ;;
esac

exit 0
