#!/bin/bash
# Restart loop scenario - repeatedly crashes

RUN_DURATION=${RUN_DURATION:-3}
EXIT_CODE=${EXIT_CODE:-1}

echo "[$(date)] Restart loop scenario starting (run #${RESTART_COUNT:-0})"
echo "[$(date)] Will run for $RUN_DURATION seconds then exit with code $EXIT_CODE"

sleep "$RUN_DURATION"

echo "[$(date)] Crashing to trigger restart"
exit "$EXIT_CODE"
