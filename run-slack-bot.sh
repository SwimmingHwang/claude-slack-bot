#!/bin/bash
# Run Claude Slack Bot
#
# Before running, create a .env file:
#   cp .env.example .env
#   # Fill in your Slack tokens

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add common paths for claude CLI
export PATH="$HOME/.claude/bin:$HOME/bin:$HOME/.local/bin:$PATH"

# Load .env if exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "Loading .env file..."
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)
fi

# Check required environment variables
if [ -z "$SLACK_BOT_TOKEN" ] || [ -z "$SLACK_APP_TOKEN" ]; then
    echo "Error: Missing required environment variables"
    echo ""
    echo "1. Copy the example env file:"
    echo "   cp .env.example .env"
    echo ""
    echo "2. Fill in your Slack tokens in .env"
    exit 1
fi

# Activate venv if exists
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Check if dependencies are installed
if ! python3 -c "import slack_bolt" 2>/dev/null; then
    echo "Installing dependencies..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    source "$SCRIPT_DIR/.venv/bin/activate"
    pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# Check if claude is available
if ! command -v claude &> /dev/null; then
    echo "Error: 'claude' CLI not found in PATH"
    echo "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
fi

echo "Starting Claude Slack Bot..."
echo ""

python3 "$SCRIPT_DIR/slack-claude-bot.py"
