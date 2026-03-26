#!/bin/bash
# Real-time log monitoring

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/slack-bot-debug.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "Log file not found: $LOG_FILE"
    echo "Start the bot first."
    exit 1
fi

echo "=== Claude Slack Bot Log Monitor ==="
echo "Log file: $LOG_FILE"
echo "Press Ctrl+C to stop"
echo ""

tail -f "$LOG_FILE" | grep --color=auto -E "INFO|WARNING|ERROR|DEBUG|===|ClickHouse|Claude"
