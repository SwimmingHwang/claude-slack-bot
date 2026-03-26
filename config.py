"""
Centralized configuration for Claude Slack Bot.
All settings are loaded from environment variables.
"""

import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent.resolve()
PARENT_DIR = PROJECT_ROOT.parent  # For --add-dir (access sibling projects)

# --- Slack ---
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")

# Optional: A channel for detailed review discussions (검토: prefix)
REVIEW_CHANNEL_ID = os.environ.get("SLACK_REVIEW_CHANNEL_ID", "")

# Optional: Always mention this user in responses (Slack user ID, e.g., "U05JK5UUR7U")
ALWAYS_MENTION_USER = os.environ.get("ALWAYS_MENTION_USER", "")

# --- Claude CLI ---
# Additional directory for Claude to explore (default: parent directory)
CLAUDE_ADD_DIR = os.environ.get("CLAUDE_ADD_DIR", str(PARENT_DIR))
# Timeout for Claude CLI calls (seconds)
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "1800"))  # 30 min default

# --- Thread Summarization ---
SUMMARY_THRESHOLD = int(os.environ.get("SUMMARY_THRESHOLD", "5"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
MAX_RECENT_MESSAGES = int(os.environ.get("MAX_RECENT_MESSAGES", "3"))

# --- ClickHouse (optional) ---
CLICKHOUSE_ENABLED = os.environ.get("CLICKHOUSE_ENABLED", "false").lower() == "true"
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "443"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_SECURE = os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true"
CLICKHOUSE_DEFAULT_SERVICE = os.environ.get("CLICKHOUSE_DEFAULT_SERVICE", "")

# --- Task Request ---
TASK_REQUEST_TTL_SECONDS = int(os.environ.get("TASK_REQUEST_TTL_SECONDS", "7200"))


def validate():
    """Validate required configuration."""
    errors = []
    if not SLACK_BOT_TOKEN:
        errors.append("SLACK_BOT_TOKEN is required")
    if not SLACK_APP_TOKEN:
        errors.append("SLACK_APP_TOKEN is required")
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("\nCopy .env.example to .env and fill in your values.")
        exit(1)
