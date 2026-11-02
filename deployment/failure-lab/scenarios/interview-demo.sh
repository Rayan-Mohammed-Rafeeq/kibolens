#!/bin/sh
set -eu

if [ "${DEMO_MODE:-failing}" = "healthy" ]; then
  echo "KiboLens interview demo recovered: readiness check is healthy."
  while :; do sleep 3600; done
fi

echo "KiboLens interview demo: deliberate application failure starting."
echo "KiboLens interview demo: configuration validation failed: DEMO_MODE=failing."
sleep "${FAIL_DELAY_SECONDS:-2}"
echo "KiboLens interview demo: exiting with code 42 for incident detection."
exit 42
