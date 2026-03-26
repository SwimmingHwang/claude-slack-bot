#!/bin/bash
# ============================================
# Claude Slack Bot - Interactive Setup Wizard
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
CLAUDE_MD="$SCRIPT_DIR/CLAUDE.md"

# --- Helper: ask with confirm/retry ---
# Usage: result=$(ask "Prompt text" "default_value" "validation_regex")
ask() {
    local prompt="$1"
    local default="$2"
    local validation="$3"
    local value

    while true; do
        if [ -n "$default" ]; then
            read -p "$prompt [$default]: " value
            value="${value:-$default}"
        else
            read -p "$prompt: " value
        fi

        # Validate if regex provided
        if [ -n "$validation" ] && [[ ! "$value" =~ $validation ]]; then
            echo "  Invalid input. Please try again."
            continue
        fi

        # Confirm
        echo -n "  -> $value  (OK? y/n/skip) "
        read -r confirm
        case "$confirm" in
            n|N) continue ;;       # re-enter
            s|skip) echo ""; return 1 ;;  # skip this field
            *) echo "$value"; return 0 ;;  # accept (Enter or y)
        esac
    done
}

# --- Helper: ask secret (no echo) ---
ask_secret() {
    local prompt="$1"
    local value

    while true; do
        read -sp "$prompt: " value
        echo ""
        echo -n "  -> (hidden)  (OK? y/n/skip) "
        read -r confirm
        case "$confirm" in
            n|N) continue ;;
            s|skip) echo ""; return 1 ;;
            *) echo "$value"; return 0 ;;
        esac
    done
}

# --- Helper: yes/no ---
ask_yn() {
    local prompt="$1"
    local default="${2:-N}"
    read -p "$prompt (y/N): " answer
    [[ "$answer" =~ ^[Yy]$ ]]
}

echo ""
echo "=========================================="
echo "  Claude Slack Bot - Setup Wizard"
echo "=========================================="
echo ""
echo "  Tip: Each input shows (OK? y/n/skip)"
echo "    Enter or y = accept"
echo "    n = re-enter"
echo "    skip = skip this field"
echo ""

# Check existing config
if [ -f "$ENV_FILE" ] || [ -f "$CLAUDE_MD" ]; then
    echo "  Existing config found:"
    [ -f "$ENV_FILE" ] && echo "    - .env"
    [ -f "$CLAUDE_MD" ] && echo "    - CLAUDE.md"
    echo ""
    if ! ask_yn "  Overwrite and start fresh?"; then
        echo ""
        echo "  Setup cancelled. Your existing config is untouched."
        exit 0
    fi
    echo ""
fi

# ========================================
# Step 1: Slack Tokens
# ========================================
echo "--- Step 1/5: Slack App Tokens ---"
echo ""
echo "  Create a Slack App at https://api.slack.com/apps"
echo "  Enable Socket Mode, add bot events & scopes (see README)"
echo ""

SLACK_BOT_TOKEN=$(ask "  Bot Token (xoxb-...)" "" "^xoxb-")
SLACK_APP_TOKEN=$(ask "  App Token (xapp-...)" "" "^xapp-")

# ========================================
# Step 2: Bot Persona
# ========================================
echo ""
echo "--- Step 2/5: Bot Persona ---"
echo ""

BOT_NAME=$(ask "  Bot name" "Claude Bot") || BOT_NAME="Claude Bot"
BOT_ROLE=$(ask "  Bot role" "Development assistant") || BOT_ROLE="Development assistant"

echo ""
echo "  Speaking style:"
echo "    1) Friendly and casual"
echo "    2) Professional and concise"
echo "    3) Technical and detailed"
echo "    4) Custom"
style_choice=$(ask "  Choose (1-4)" "1") || style_choice="1"

case $style_choice in
    1) SPEAKING_STYLE="Friendly and casual, uses exclamation marks, approachable" ;;
    2) SPEAKING_STYLE="Professional and concise, straight to the point" ;;
    3) SPEAKING_STYLE="Technical and detailed, includes code examples when relevant" ;;
    4) SPEAKING_STYLE=$(ask "  Describe the style" "Friendly") || SPEAKING_STYLE="Friendly" ;;
    *) SPEAKING_STYLE="Friendly and casual" ;;
esac

LANGUAGE=$(ask "  Response language" "English") || LANGUAGE="English"

echo ""
echo "  Extra persona details? (e.g., 'Loves Python, hates magic numbers')"
EXTRA_PERSONA=$(ask "  Extra details (or skip)" "") || EXTRA_PERSONA=""

# ========================================
# Step 3: Working Directory
# ========================================
echo ""
echo "--- Step 3/5: Working Directory ---"
echo ""
echo "  The codebase path Claude gets full access to explore."
echo ""

DEFAULT_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR=$(ask "  Codebase path" "$DEFAULT_DIR") || WORK_DIR="$DEFAULT_DIR"
WORK_DIR="${WORK_DIR/#\~/$HOME}"

if [ ! -d "$WORK_DIR" ]; then
    echo "  Warning: '$WORK_DIR' doesn't exist yet."
    if ! ask_yn "  Continue anyway?"; then
        echo "  Please create the directory first, then re-run setup."
        exit 1
    fi
fi

# ========================================
# Step 4: Optional Features
# ========================================
echo ""
echo "--- Step 4/5: Optional Features ---"
echo ""

# Review channel
REVIEW_CHANNEL_ID=""
if ask_yn "  Enable review channel for detailed discussions?"; then
    echo "    (Right-click channel > View channel details > ID at bottom)"
    REVIEW_CHANNEL_ID=$(ask "    Review Channel ID (C...)" "" "^C") || REVIEW_CHANNEL_ID=""
fi

# Always mention user
ALWAYS_MENTION_USER=""
if ask_yn "  Always mention a specific user in responses?"; then
    echo "    (Click profile > ... > Copy member ID)"
    ALWAYS_MENTION_USER=$(ask "    User ID (U...)" "" "^U") || ALWAYS_MENTION_USER=""
fi

# ClickHouse
CLICKHOUSE_ENABLED="false"
CLICKHOUSE_HOST=""
CLICKHOUSE_USER=""
CLICKHOUSE_PASSWORD=""
CLICKHOUSE_DEFAULT_SERVICE=""
if ask_yn "  Enable ClickHouse integration?"; then
    CLICKHOUSE_ENABLED="true"
    CLICKHOUSE_HOST=$(ask "    ClickHouse host" "") || CLICKHOUSE_HOST=""
    CLICKHOUSE_USER=$(ask "    ClickHouse user" "default") || CLICKHOUSE_USER="default"
    CLICKHOUSE_PASSWORD=$(ask_secret "    ClickHouse password") || CLICKHOUSE_PASSWORD=""
    CLICKHOUSE_DEFAULT_SERVICE=$(ask "    Default service name" "") || CLICKHOUSE_DEFAULT_SERVICE=""
fi

# ========================================
# Step 5: Team Members
# ========================================
echo ""
echo "--- Step 5/5: Team Members (optional) ---"
echo ""
echo "  Format: Name,email@example.com"
echo "  Press Enter on empty line to finish."
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
        echo "    Added: $name <$email>"
    else
        echo "    Invalid format. Use: Name,email@example.com"
    fi
done

# ========================================
# Review before saving
# ========================================
echo ""
echo "=========================================="
echo "  Review Your Settings"
echo "=========================================="
echo ""
echo "  Bot name:     $BOT_NAME"
echo "  Role:         $BOT_ROLE"
echo "  Style:        $SPEAKING_STYLE"
echo "  Language:     $LANGUAGE"
echo "  Codebase:     $WORK_DIR"
echo "  Review ch:    ${REVIEW_CHANNEL_ID:-not set}"
echo "  Mention user: ${ALWAYS_MENTION_USER:-not set}"
echo "  ClickHouse:   $CLICKHOUSE_ENABLED"
echo ""

if ! ask_yn "  Save this configuration?"; then
    echo ""
    echo "  Setup cancelled. Nothing was saved."
    echo "  Run ./setup.sh again to restart."
    exit 0
fi

# ========================================
# Generate files
# ========================================
echo ""
echo "Saving configuration..."

# --- .env ---
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

# --- CLAUDE.md ---
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

if [ -n "$TEAM_TABLE" ]; then
    cat >> "$CLAUDE_MD" << TEAMEOF

## Team Members

| Name | Email |
|------|-------|
${TEAM_TABLE}
TEAMEOF
fi

echo "  Created: CLAUDE.md"

# --- venv & deps ---
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
echo "  To start the bot:"
echo "    ./run-slack-bot.sh"
echo ""
echo "  To customize further:"
echo "    - Edit CLAUDE.md for persona/behavior"
echo "    - Edit .env for tokens/features"
echo "    - Re-run ./setup.sh to start over"
echo ""
