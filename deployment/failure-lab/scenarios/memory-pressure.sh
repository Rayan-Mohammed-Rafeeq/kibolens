#!/bin/bash
# Memory pressure scenario - controlled memory consumption

DURATION=${DURATION:-60}
MEMORY_MB=${MEMORY_MB:-128}

echo "[$(date)] Memory pressure scenario starting..."
echo "[$(date)] Will allocate ${MEMORY_MB}MB for $DURATION seconds"
echo "[$(date)] Memory usage capped by container limits"

# Use stress-ng to allocate memory
stress-ng --vm 1 --vm-bytes "${MEMORY_MB}M" --timeout "${DURATION}s" --metrics-brief

echo "[$(date)] Memory pressure completed"
