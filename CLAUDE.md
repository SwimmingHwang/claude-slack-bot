# Claude Slack Bot

A Slack bot powered by Claude Code CLI. You are currently helping set up or maintain this bot.

## Setup Guide (for Claude)

When a user opens this project and says "setup", "set up", "install", or similar, follow this interactive setup flow. Ask one section at a time, confirm, then move on.

### Setup Flow

**Step 1: Check prerequisites**
- Confirm `claude` CLI is available (`which claude`)
- Confirm Python 3.10+ is available (`python3 --version`)
- Check if `.env` already exists - if so, ask if they want to reconfigure

**Step 2: Slack App tokens**
Ask the user for:
- Bot Token (`xoxb-...`) - from Slack App > OAuth & Permissions
- App Token (`xapp-...`) - from Slack App > Basic Information > App-Level Tokens

If they haven't created a Slack App yet, guide them:
1. Go to https://api.slack.com/apps and create a new app
2. Enable Socket Mode, create App-Level Token with `connections:write` scope
3. Subscribe to bot events: `app_mention`, `message.channels`, `message.groups`, `message.im`
4. Add bot scopes: `app_mentions:read`, `channels:history`, `groups:history`, `im:history`, `chat:write`, `reactions:read`, `reactions:write`, `users:read`
5. Install to workspace

**Step 3: Bot persona**
Ask the user:
- Bot name (e.g., "DevBot", "CodeHelper")
- Bot role (e.g., "Backend developer assistant")
- Speaking style: friendly/professional/technical/custom
- Response language (Korean, English, etc.)
- Any extra personality traits

**Step 4: Working directory**
Ask which codebase directory the bot should explore when answering questions.
This path goes into `CLAUDE_ADD_DIR` in `.env` and also `--add-dir` when calling Claude CLI.

**Step 5: Optional features**
Ask about each:
- Review channel ID (for `review:` prefix discussions)
- Always-mention user ID (gets pinged on every response)
- ClickHouse integration (host, user, password, default service)
- Team members (name + email pairs for calendar features)

**Step 6: Generate files**
Create two files from the collected info:

1. `.env` - Use `.env.example` as template, fill in values
2. `CLAUDE.md` - Overwrite THIS file with the bot's actual persona config (see template below)

**Step 7: Install dependencies**
Run: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

**Step 8: Confirm**
Show summary and tell user to run `./run-slack-bot.sh`

### CLAUDE.md Template (for generated bot persona)

After setup, replace this file's contents with:

```markdown
# {Bot Name}

Slack Bot powered by Claude Code CLI.

## Bot Persona

**Name**: {name}
**Role**: {role}

### Speaking Style
- Language: {language}
- Style: {style}
- {extra traits if any}

### Behavior Rules
1. Answer accurately based on the codebase
2. If unsure, say so honestly - never make things up
3. Be helpful and concise

## Working Directory

Claude explores: `{path}`

## Slack Message Formatting (CRITICAL)

This bot sends messages via Slack - use Slack mrkdwn format:
- Bold: `*text*` (NOT `**text**`)
- Italic: `_text_` (NOT `*text*`)
- Link: `<url|display text>` (NOT `[text](url)`)
- Use `*bold text*` for section titles instead of `##` headers
- Use bullet lists (`-`) instead of tables

## Team Members (if provided)

| Name | Email |
|------|-------|
| ... | ... |
```

## Project Structure

```
slack-claude-bot.py      # Main bot application
config.py                # Centralized config (reads .env)
query_clickhouse.py      # ClickHouse integration (optional)
slack_user_cache.py      # User email cache utility
run-slack-bot.sh         # Start script (auto-installs deps)
setup.sh                 # Bash setup wizard (alternative to Claude-guided setup)
watch-logs.sh            # Log monitoring
.env.example             # Configuration template
```

## How It Works

1. Bot runs in Slack Socket Mode (no public URL needed)
2. When mentioned, it calls `claude -p <prompt> --dangerously-skip-permissions --add-dir <codebase>`
3. Claude explores the codebase and responds
4. Response is posted back to Slack thread

## Key Config (config.py)

All settings come from environment variables (`.env` file):
- `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` - Required Slack tokens
- `CLAUDE_ADD_DIR` - Codebase path for Claude to explore
- `ALWAYS_MENTION_USER` - Optional user to always ping
- `SLACK_REVIEW_CHANNEL_ID` - Optional review discussion channel
- `CLICKHOUSE_ENABLED` + connection vars - Optional log query feature
