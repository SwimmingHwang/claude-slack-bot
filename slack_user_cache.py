#!/usr/bin/env python3
"""
Slack User Cache - SQLite-based email lookup.

Fetches Slack workspace users (requires users:read.email scope) and caches
them in a local SQLite database for quick name-to-email lookups.

Usage:
    python3 slack_user_cache.py sync           # Sync users from Slack
    python3 slack_user_cache.py search "name"  # Search users by name
    python3 slack_user_cache.py emails "a" "b" # Get emails for names
    python3 slack_user_cache.py list            # List all cached users
"""

import os
import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "slack_users.db"
CACHE_TTL_SECONDS = 86400  # 24 hours


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS slack_users (
            slack_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            real_name TEXT,
            display_name TEXT,
            email TEXT,
            title TEXT,
            is_bot INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_email ON slack_users(email);
        CREATE INDEX IF NOT EXISTS idx_real_name ON slack_users(real_name);
        CREATE INDEX IF NOT EXISTS idx_username ON slack_users(username);
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def sync_from_slack(slack_client) -> dict:
    """Fetch all users from Slack and upsert into SQLite."""
    init_db()
    conn = get_db()
    now = int(time.time())
    stats = {"total": 0, "with_email": 0, "upserted": 0}

    cursor = None
    while True:
        kwargs = {"limit": 200}
        if cursor:
            kwargs["cursor"] = cursor

        response = slack_client.users_list(**kwargs)
        members = response.get("members", [])

        for member in members:
            if member.get("id") == "USLACKBOT":
                continue
            stats["total"] += 1
            profile = member.get("profile", {})
            email = profile.get("email", "")
            if email:
                stats["with_email"] += 1

            conn.execute("""
                INSERT INTO slack_users
                    (slack_id, username, real_name, display_name, email, title, is_bot, is_deleted, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slack_id) DO UPDATE SET
                    username=excluded.username, real_name=excluded.real_name,
                    display_name=excluded.display_name, email=excluded.email,
                    title=excluded.title, is_bot=excluded.is_bot,
                    is_deleted=excluded.is_deleted, updated_at=excluded.updated_at
            """, (
                member["id"], member.get("name", ""), member.get("real_name", ""),
                profile.get("display_name", ""), email, profile.get("title", ""),
                1 if member.get("is_bot") else 0,
                1 if member.get("deleted") else 0,
                now,
            ))
            stats["upserted"] += 1

        conn.commit()
        cursor = response.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break

    conn.execute("""
        INSERT INTO sync_metadata (key, value) VALUES ('last_sync', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (str(now),))
    conn.commit()
    conn.close()
    logger.info(f"Slack user sync complete: {stats}")
    return stats


def needs_sync() -> bool:
    if not DB_PATH.exists():
        return True
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM sync_metadata WHERE key = 'last_sync'").fetchone()
        conn.close()
        if not row:
            return True
        return (int(time.time()) - int(row["value"])) > CACHE_TTL_SECONDS
    except Exception:
        return True


def search_users(query: str, include_bots: bool = False) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = get_db()
    pattern = f"%{query}%"
    bot_filter = "" if include_bots else "AND is_bot = 0 AND is_deleted = 0"
    rows = conn.execute(f"""
        SELECT slack_id, username, real_name, display_name, email, title
        FROM slack_users
        WHERE (real_name LIKE ? OR display_name LIKE ? OR username LIKE ? OR email LIKE ?)
        {bot_filter}
        ORDER BY real_name
    """, (pattern, pattern, pattern, pattern)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_email(name: str) -> Optional[str]:
    results = search_users(name)
    if results and results[0].get("email"):
        return results[0]["email"]
    return None


def get_emails(names: list[str]) -> dict[str, Optional[str]]:
    return {name: get_email(name) for name in names}


# CLI
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "sync":
        from slack_sdk import WebClient
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            print("Error: SLACK_BOT_TOKEN not set")
            sys.exit(1)
        stats = sync_from_slack(WebClient(token=token))
        print(f"Synced {stats['upserted']} users ({stats['with_email']} with email)")
    elif command == "search":
        query = " ".join(sys.argv[2:])
        for u in search_users(query):
            print(f"  {u['real_name']:<20} {u.get('email', ''):<35} {u['slack_id']}")
    elif command == "emails":
        for name in sys.argv[2:]:
            print(f"{name}: {get_email(name) or 'not found'}")
    elif command == "list":
        for u in search_users(""):
            print(f"  {u['real_name']:<20} {u.get('email', ''):<35} {u['slack_id']}")
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
