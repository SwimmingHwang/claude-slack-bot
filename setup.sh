#!/bin/bash
# ============================================
# Claude Slack Bot - Interactive Setup Wizard
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
CLAUDE_MD="$SCRIPT_DIR/CLAUDE.md"

echo ""
echo "=========================================="
echo "  Claude Slack Bot - Setup Wizard"
echo "=========================================="
echo ""

# Check if already configured
if [ -f "$ENV_FILE" ] && [ -f "$CLAUDE_MD" ]; then
    read -p "Configuration already exists. Overwrite? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# --- Step 1: Slack Tokens ---
echo ""
echo "--- Step 1/5: Slack App Tokens ---"
echo ""
echo "Create a Slack App at https://api.slack.com/apps"
echo "  - Enable Socket Mode"
echo "  - Add bot events: app_mention, message.channels, message.groups, message.im"
echo "  - Add scopes: app_mentions:read, channels:history, chat:write, reactions:write"
echo ""

read -p "Bot Token (xoxb-...): " SLACK_BOT_TOKEN
while [[ ! "$SLACK_BOT_TOKEN" =~ ^xoxb- ]]; do
    echo "  Token must start with 'xoxb-'"
    read -p "Bot Token (xoxb-...): " SLACK_BOT_TOKEN
done

read -p "App Token (xapp-...): " SLACK_APP_TOKEN
while [[ ! "$SLACK_APP_TOKEN" =~ ^xapp- ]]; do
    echo "  Token must start with 'xapp-'"
    read -p "App Token (xapp-...): " SLACK_APP_TOKEN
done

# --- Step 2: Bot Persona ---
echo ""
echo "--- Step 2/5: Bot Persona ---"
echo ""
echo "Give your bot a personality! This goes into CLAUDE.md"
echo "so Claude knows how to behave."
echo ""

read -p "Bot name (e.g., DevBot, CodeHelper): " BOT_NAME
BOT_NAME="${BOT_NAME:-Claude Bot}"

read -p "Bot role (e.g., Backend developer assistant): " BOT_ROLE
BOT_ROLE="${BOT_ROLE:-Development assistant}"

echo ""
echo "Speaking style examples:"
echo "  1) Friendly and casual"
echo "  2) Professional and concise"
echo "  3) Technical and detailed"
echo "  4) Custom"
read -p "Choose style (1-4) [1]: " style_choice
style_choice="${style_choice:-1}"

case $style_choice in
    1) SPEAKING_STYLE="Friendly and casual, uses exclamation marks, approachable" ;;
    2) SPEAKING_STYLE="Professional and concise, straight to the point" ;;
    3) SPEAKING_STYLE="Technical and detailed, includes code examples when relevant" ;;
    4) read -p "Describe the speaking style: " SPEAKING_STYLE ;;
    *) SPEAKING_STYLE="Friendly and casual" ;;
esac

read -p "Response language (e.g., Korean, English, Japanese) [English]: " LANGUAGE
LANGUAGE="${LANGUAGE:-English}"

echo ""
echo "Any extra persona details? (press Enter to skip)"
echo "  e.g., 'Loves Python, always suggests tests, hates magic numbers'"
read -p "> " EXTRA_PERSONA

# --- Step 3: Working Directory ---
echo ""
echo "--- Step 3/5: Working Directory ---"
echo ""
echo "Claude will explore this directory to answer code questions."
echo "This is the codebase Claude gets full access to."
echo ""

read -p "Codebase path [$(dirname "$SCRIPT_DIR")]: " WORK_DIR
WORK_DIR="${WORK_DIR:-$(dirname "$SCRIPT_DIR")}"

# Expand ~ to home directory
WORK_DIR="${WORK_DIR/#\~/$HOME}"

# Validate path
if [ ! -d "$WORK_DIR" ]; then
    echo "  Warning: '$WORK_DIR' doesn't exist yet."
    read -p "  Continue anyway? (y/N): " continue_anyway
    if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
        echo "  Please create the directory first."
        exit 1
    fi
fi

# --- Step 4: Optional Features ---
echo ""
echo "--- Step 4/5: Optional Features ---"
echo ""

# Review channel
read -p "Enable review channel for detailed discussions? (y/N): " enable_review
REVIEW_CHANNEL_ID=""
if [[ "$enable_review" =~ ^[Yy]$ ]]; then
    echo "  Create a channel in Slack for review discussions, then paste the channel ID."
    echo "  (Right-click channel > View channel details > scroll to bottom for ID)"
    read -p "  Review Channel ID (C...): " REVIEW_CHANNEL_ID
fi

# Always mention user
read -p "Always mention a specific user in responses? (y/N): " enable_mention
ALWAYS_MENTION_USER=""
if [[ "$enable_mention" =~ ^[Yy]$ ]]; then
    echo "  Paste the Slack user ID to always mention."
    echo "  (Click on profile > three dots > Copy member ID)"
    read -p "  User ID (U...): " ALWAYS_MENTION_USER
fi

# ClickHouse
read -p "Enable ClickHouse integration? (y/N): " enable_ch
CLICKHOUSE_ENABLED="false"
CLICKHOUSE_HOST=""
CLICKHOUSE_USER=""
CLICKHOUSE_PASSWORD=""
CLICKHOUSE_DEFAULT_SERVICE=""
if [[ "$enable_ch" =~ ^[Yy]$ ]]; then
    CLICKHOUSE_ENABLED="true"
    read -p "  ClickHouse host: " CLICKHOUSE_HOST
    read -p "  ClickHouse user [default]: " CLICKHOUSE_USER
    CLICKHOUSE_USER="${CLICKHOUSE_USER:-default}"
    read -sp "  ClickHouse password: " CLICKHOUSE_PASSWORD
    echo ""
    read -p "  Default service name: " CLICKHOUSE_DEFAULT_SERVICE
fi

# --- Step 5: Team Members ---
echo ""
echo "--- Step 5/5: Team Members (optional) ---"
echo ""
echo "Add team members for calendar/mention features."
echo "Enter in format: Name,email@example.com"
echo "Press Enter on empty line to finish."
echo ""

TEAM_TABLE=""
while true; do
    read -p "  Name,email (or Enter to finish): " member
    if [ -z "$member" ]; then
        break
    fi
    IFS=',' read -r name email <<< "$member"
    name=$(echo "$name" | xargs)
    email=$(echo "$email" | xargs)
    if [ -n "$name" ] && [ -n "$email" ]; then
        TEAM_TABLE="${TEAM_TABLE}| ${name} | ${email} |
"
    else
        echo "    Invalid format. Use: Name,email@example.com"
    fi
done

# === Generate .env ===
echo ""
echo "Generating .env..."

cat > "$ENV_FILE" << ENVEOF
# Claude Slack Bot Configuration
# Generated by setup.sh on $(date '+%Y-%m-%d %H:%M')

# Slack Tokens
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
SLACK_APP_TOKEN=${SLACK_APP_TOKEN}

# Bot Behavior
ALWAYS_MENTION_USER=${ALWAYS_MENTION_USER}
SLACK_REVIEW_CHANNEL_ID=${REVIEW_CHANNEL_ID}
CLAUDE_ADD_DIR=${WORK_DIR}
CLAUDE_TIMEOUT=1800

# ClickHouse (optional)
CLICKHOUSE_ENABLED=${CLICKHOUSE_ENABLED}
CLICKHOUSE_HOST=${CLICKHOUSE_HOST}
CLICKHOUSE_PORT=443
CLICKHOUSE_USER=${CLICKHOUSE_USER}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
CLICKHOUSE_SECURE=true
CLICKHOUSE_DEFAULT_SERVICE=${CLICKHOUSE_DEFAULT_SERVICE}
ENVEOF

echo "  Created: .env"

# === Generate CLAUDE.md ===
echo "Generating CLAUDE.md..."

cat > "$CLAUDE_MD" << CLAUDEEOF
# ${BOT_NAME}

Slack Bot powered by Claude Code CLI.

## Bot Persona

**Name**: ${BOT_NAME}
**Role**: ${BOT_ROLE}

### Speaking Style

- Language: ${LANGUAGE}
- Style: ${SPEAKING_STYLE}
$([ -n "$EXTRA_PERSONA" ] && echo "- Extra: ${EXTRA_PERSONA}")

### Behavior Rules

1. Answer accurately based on the codebase
2. If unsure, say so honestly - never make things up
3. Be helpful and concise
$([ -n "$ALWAYS_MENTION_USER" ] && echo "4. Always mention <@${ALWAYS_MENTION_USER}> for visibility")

## Working Directory

Claude explores: \`${WORK_DIR}\`

## Slack Message Formatting (CRITICAL)

This bot sends messages via Slack - use Slack mrkdwn format:

- Bold: \`*text*\` (NOT \`**text**\`)
- Italic: \`_text_\` (NOT \`*text*\`)
- Link: \`<url|display text>\` (NOT \`[text](url)\`)
- Use \`*bold text*\` for section titles instead of \`##\` headers
- Use bullet lists (\`-\`) instead of tables
CLAUDEEOF

# Add team table if provided
if [ -n "$TEAM_TABLE" ]; then
    cat >> "$CLAUDE_MD" << TEAMEOF

## Team Members

| Name | Email |
|------|-------|
${TEAM_TABLE}
TEAMEOF
fi

echo "  Created: CLAUDE.md"

# === Setup venv & dependencies ===
echo ""
echo "Setting up Python environment..."

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    python3 -m venv "$SCRIPT_DIR/.venv"
fi
source "$SCRIPT_DIR/.venv/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "  Bot name:    ${BOT_NAME}"
echo "  Language:    ${LANGUAGE}"
echo "  Codebase:    ${WORK_DIR}"
echo "  ClickHouse:  ${CLICKHOUSE_ENABLED}"
echo "  Review ch:   ${REVIEW_CHANNEL_ID:-not set}"
echo ""
echo "  Files created:"
echo "    - .env       (tokens & config)"
echo "    - CLAUDE.md  (bot persona & rules)"
echo ""
echo "  To start the bot:"
echo "    ./run-slack-bot.sh"
echo ""
echo "  To customize further, edit CLAUDE.md"
echo ""
