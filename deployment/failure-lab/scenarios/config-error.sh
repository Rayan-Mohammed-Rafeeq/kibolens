#!/bin/bash
# Config error scenario - application rejects invalid configuration

CONFIG_FILE=${CONFIG_FILE:-/app/config.json}

echo "[$(date)] Config error scenario starting..."
echo "[$(date)] Loading configuration from: $CONFIG_FILE"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[$(date)] ERROR: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

echo "[$(date)] Validating configuration..."
CONFIG_CONTENT=$(cat "$CONFIG_FILE")
echo "[$(date)] Config content: $CONFIG_CONTENT"

# Check for required fields
if ! echo "$CONFIG_CONTENT" | grep -q '"database"'; then
    echo "[$(date)] ERROR: Missing required field 'database' in configuration"
    exit 1
fi

if ! echo "$CONFIG_CONTENT" | grep -q '"port"'; then
    echo "[$(date)] ERROR: Missing required field 'port' in configuration"
    exit 1
fi

# Validate JSON syntax (basic check)
if ! echo "$CONFIG_CONTENT" | grep -q '{'; then
    echo "[$(date)] ERROR: Invalid JSON syntax in configuration"
    exit 1
fi

echo "[$(date)] ERROR: Configuration validation failed"
echo "[$(date)] Review configuration and restart application"
exit 1
