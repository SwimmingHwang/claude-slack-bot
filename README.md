# Claude Slack Bot

A Slack bot powered by [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) that answers questions about your codebase directly in Slack.

## Features

- **Mention-based Q&A** - Mention the bot in any channel to get AI-powered answers about your code
- **Thread awareness** - Follows conversation context with smart thread summarization
- **Response styles** - Control response verbosity with prefixes:
  - `summary:` - Concise 1-2 paragraph answer (default)
  - `detailed:` - Comprehensive detailed answer
  - `review:` - Creates a separate discussion thread in a review channel
  - `task:` - Interactive clarification before starting work
- **DM support** - Send direct messages to the bot
- **ClickHouse integration** (optional) - Query OpenTelemetry traces for error analysis
- **User cache** - SQLite-based Slack user email lookup for calendar integrations
- **Auto-reconnect** - Automatically restarts on connection failures

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- A Slack workspace with admin access to create apps

## Quick Start

### 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. **Socket Mode**: Enable it, create an App-Level Token with `connections:write` scope
3. **Event Subscriptions**: Enable and subscribe to bot events:
   - `app_mention`
   - `message.channels`
   - `message.groups`
   - `message.im`
4. **OAuth & Permissions**: Add these bot token scopes:
   - `app_mentions:read`
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `chat:write`
   - `reactions:read`
   - `reactions:write`
   - `users:read`
   - `users:read.email` (optional, for user cache)
5. Install the app to your workspace

### 2. Setup with Claude Code (Recommended)

```bash
git clone https://github.com/SwimmingHwang/claude-slack-bot.git
cd claude-slack-bot
claude
```

Then just say:

```
> setup
```

Claude will interactively guide you through:
- Slack token configuration
- Bot persona (name, role, speaking style, language)
- Working directory (the codebase Claude explores)
- Optional features (review channel, ClickHouse, team members)
- Auto-generates `.env` and `CLAUDE.md`
- Installs dependencies

### 3. Run

```bash
./run-slack-bot.sh
```

> **Alternative**: Run `./setup.sh` for a bash-based setup wizard, or copy `.env.example` to `.env` and edit manually.

## Configuration

All settings are in `.env` (see `.env.example` for all options):

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | App-Level Token (`xapp-...`) |
| `ALWAYS_MENTION_USER` | No | Always mention this Slack user ID in responses |
| `SLACK_REVIEW_CHANNEL_ID` | No | Channel for `review:` and `task:` discussions |
| `CLAUDE_ADD_DIR` | No | Additional directory for Claude to explore |
| `CLAUDE_TIMEOUT` | No | CLI timeout in seconds (default: 1800) |
| `CLICKHOUSE_ENABLED` | No | Enable ClickHouse integration (`true`/`false`) |

## Usage

### Basic Questions

```
@bot What does the auth middleware do?
@bot How is the user model structured?
```

### Response Styles

```
@bot summary: How does login work?          # Brief answer
@bot detailed: Explain the auth flow         # Full explanation
@bot review: Should we refactor the DB layer? # Separate review thread
@bot task: Add rate limiting to the API      # Interactive task clarification
```

### ClickHouse Queries (when enabled)

```
@bot 500 errors                    # Recent HTTP 500 errors
@bot slow requests                 # Slow request analysis
@bot stats                         # Service statistics
@bot trace abc123...               # Trace by ID
@bot services                      # List available services
```

## Project Structure

```
claude-slack-bot/
  slack-claude-bot.py      # Main bot application
  config.py                # Centralized configuration
  query_clickhouse.py      # ClickHouse integration (optional)
  slack_user_cache.py      # User email cache utility
  run-slack-bot.sh         # Start script
  watch-logs.sh            # Log monitoring
  .env.example             # Configuration template
  requirements.txt         # Python dependencies
```

## Customization

### Adding a Bot Persona

Edit the prompt in `call_claude_code()` in `slack-claude-bot.py` to add personality:

```python
prompt = f"""You are [Your Bot Name], a friendly assistant for the [Team] team.
You speak in [style] and focus on [domain].
...
"""
```

### Adding a CLAUDE.md

Create a `CLAUDE.md` file in the project root to give Claude Code persistent context about your codebase, team conventions, and bot behavior.

## License

MIT
