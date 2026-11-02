#!/bin/bash
# CPU stress scenario - controlled CPU load

DURATION=${DURATION:-60}
CPU_WORKERS=${CPU_WORKERS:-1}

echo "[$(date)] CPU stress scenario starting..."
echo "[$(date)] Running $CPU_WORKERS CPU workers for $DURATION seconds"
echo "[$(date)] CPU will be at 100% load (capped by container limits)"

# Run stress-ng with CPU stressor
stress-ng --cpu "$CPU_WORKERS" --timeout "${DURATION}s" --metrics-brief

echo "[$(date)] CPU stress completed"
