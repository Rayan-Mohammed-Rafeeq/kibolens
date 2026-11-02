#!/bin/bash
# Missing dependency scenario - required file/service unavailable

REQUIRED_FILE=${REQUIRED_FILE:-/app/required-config.json}
RETRY_COUNT=${RETRY_COUNT:-3}
RETRY_DELAY=${RETRY_DELAY:-2}

echo "[$(date)] Missing dependency scenario starting..."
echo "[$(date)] Checking for required dependency: $REQUIRED_FILE"

for i in $(seq 1 "$RETRY_COUNT"); do
    if [ -f "$REQUIRED_FILE" ]; then
        echo "[$(date)] Dependency found: $REQUIRED_FILE"
        echo "[$(date)] Application running successfully"
        
        # Keep running
        while true; do
            echo "[$(date)] Application healthy"
            sleep 10
        done
    else
        echo "[$(date)] Attempt $i/$RETRY_COUNT: Dependency not found: $REQUIRED_FILE"
        if [ "$i" -lt "$RETRY_COUNT" ]; then
            echo "[$(date)] Retrying in $RETRY_DELAY seconds..."
            sleep "$RETRY_DELAY"
        fi
    fi
done

echo "[$(date)] ERROR: Required dependency $REQUIRED_FILE not found after $RETRY_COUNT attempts"
echo "[$(date)] Application cannot start"
exit 1
