#!/bin/bash
# Unhealthy scenario - runs but health check fails

HEALTHY_DURATION=${HEALTHY_DURATION:-30}
HEALTH_CHECK_FILE="/tmp/healthy"

echo "[$(date)] Unhealthy scenario starting..."
echo "[$(date)] Will be healthy for $HEALTHY_DURATION seconds, then fail health check"

# Start healthy
touch "$HEALTH_CHECK_FILE"
echo "[$(date)] Health check enabled at $HEALTH_CHECK_FILE"

# Wait configured duration
sleep "$HEALTHY_DURATION"

# Remove health check file to simulate unhealthy state
rm -f "$HEALTH_CHECK_FILE"
echo "[$(date)] Health check disabled - container is now unhealthy"

# Keep running but unhealthy
while true; do
    echo "[$(date)] Still running but unhealthy..."
    sleep 10
done
