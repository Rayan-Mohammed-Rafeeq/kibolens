#!/bin/bash
# Crasher scenario - exits with configured exit code after delay

EXIT_CODE=${EXIT_CODE:-137}
DELAY_SECONDS=${DELAY_SECONDS:-5}

echo "[$(date)] Crasher scenario starting..."
echo "[$(date)] Will exit with code $EXIT_CODE after $DELAY_SECONDS seconds"

sleep "$DELAY_SECONDS"

echo "[$(date)] Crashing now with exit code $EXIT_CODE"
exit "$EXIT_CODE"
