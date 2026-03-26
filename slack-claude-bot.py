#!/usr/bin/env python3
"""
Slack Bot that responds to mentions using Claude Code CLI.
Uses Socket Mode for local development (no public URL needed).

Features:
- Mention bot in any channel for AI-powered answers
- Thread context awareness with smart summarization
- Response style prefixes: summary/detailed/review/task_request
- Optional ClickHouse integration for log queries
- Review channel for in-depth discussions
- Task request mode with interactive clarification

Usage:
    cp .env.example .env  # Fill in your tokens
    ./run-slack-bot.sh
"""

import os
import subprocess
import re
import logging
import time
import sys
from dataclasses import dataclass, field
from typing import Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Load config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
config.validate()

# Optional ClickHouse
if config.CLICKHOUSE_ENABLED:
    try:
        import query_clickhouse
    except ImportError:
        logging.warning("clickhouse-connect not installed. ClickHouse features disabled.")
        config.CLICKHOUSE_ENABLED = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

file_handler = logging.FileHandler('slack-bot-debug.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Initialize Slack app
app = App(token=config.SLACK_BOT_TOKEN)

# Cached bot user ID
_bot_user_id: Optional[str] = None


def get_bot_user_id(client) -> str:
    """Get bot user ID with caching."""
    global _bot_user_id
    if _bot_user_id is None:
        _bot_user_id = client.auth_test()["user_id"]
    return _bot_user_id


# --- Thread Summary Cache ---
@dataclass
class ThreadCache:
    summary: str
    message_count: int
    last_updated: float = field(default_factory=time.time)


thread_summaries: dict[str, ThreadCache] = {}

# Review thread tracking: {original_channel:original_ts -> review_channel:review_ts}
review_threads: dict[str, str] = {}


# --- Task Request State ---
@dataclass
class TaskRequestState:
    original_question: str
    clarification_history: list
    original_user: str
    original_channel: str
    original_ts: str
    created_at: float = field(default_factory=time.time)


task_requests: dict[str, TaskRequestState] = {}


def cleanup_expired_task_requests():
    current_time = time.time()
    expired = [k for k, v in task_requests.items()
               if current_time - v.created_at > config.TASK_REQUEST_TTL_SECONDS]
    for key in expired:
        del task_requests[key]
        logger.info(f"Cleaned up expired task request: {key}")


def extract_question(text: str, bot_user_id: str) -> str:
    return re.sub(rf'<@{bot_user_id}>\s*', '', text).strip()


def detect_response_style(text: str, bot_user_id: str) -> tuple[str, str]:
    """
    Detect command prefix and return (cleaned_question, response_style).

    Prefixes:
    - "summary:" -> concise 1-2 paragraphs
    - "detailed:" -> full detailed answer
    - "review:" -> separate discussion channel
    - "task:" -> interactive clarification + feature dev
    - Default -> summary
    """
    cleaned = re.sub(rf'<@{bot_user_id}>\s*', '', text).strip()

    prefixes = {
        "summary:": "summary",
        "detailed:": "detailed",
        "review:": "review",
        "task:": "task_request",
    }

    for prefix, style in prefixes.items():
        if cleaned.lower().startswith(prefix):
            return cleaned[len(prefix):].strip(), style

    return cleaned, "summary"


ERROR_PREFIXES = ("Claude CLI error:", "Request timed out", "Claude CLI not found", "Error:")


def is_error_response(response: str) -> bool:
    return any(response.startswith(p) for p in ERROR_PREFIXES)


def notify_error_to_owner(client, error_detail: str, user: str, channel: str, question: str):
    """DM the bot owner about errors."""
    if not config.ALWAYS_MENTION_USER:
        return
    try:
        dm = client.conversations_open(users=[config.ALWAYS_MENTION_USER])
        client.chat_postMessage(
            channel=dm["channel"]["id"],
            text=(
                f"*Bot Response Error*\n"
                f"- User: <@{user}>\n"
                f"- Channel: <#{channel}>\n"
                f"- Question: {question[:200]}\n"
                f"- Error: {error_detail[:500]}"
            )
        )
    except Exception as e:
        logger.error(f"Failed to send error DM: {e}")


def call_claude_code(question: str, context: str = "", response_style: str = "summary") -> str:
    """Call Claude Code CLI with the question and return the response."""
    style_instructions = {
        "summary": """
**Response Style: SUMMARY**
- Keep response CONCISE (1-2 paragraphs max)
- Focus on the direct answer only
- Be brief - this is a busy thread
""",
        "detailed": """
**Response Style: DETAILED**
- Provide a comprehensive, detailed answer
- Include explanations, examples, and reasoning
- Use structured format with clear sections
""",
        "review": """
**Response Style: REVIEW**
- Provide a BRIEF summary of your understanding
- Then suggest moving to a separate channel for detailed discussion
""",
    }

    style_note = style_instructions.get(response_style, style_instructions["summary"])

    prompt = f"""You are a helpful Slack bot powered by Claude Code.
You can explore code in the project directory and answer questions about the codebase.

Question: {question}

{f"Thread context: {context}" if context else ""}

{style_note}

Please provide a helpful answer based on the codebase.

**Slack Formatting (mrkdwn, NOT GitHub Markdown):**
- Bold: *text* (NOT **text**)
- Use *bold* for section titles instead of ## headers
- Use bullet lists (-) instead of tables
- Links: <url|display text> (NOT [text](url))
"""

    try:
        cmd = [
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
        ]
        if config.CLAUDE_ADD_DIR:
            cmd.extend(["--add-dir", config.CLAUDE_ADD_DIR])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(config.PROJECT_ROOT),
            timeout=config.CLAUDE_TIMEOUT,
        )

        if result.returncode == 0:
            response = result.stdout.strip()
            if len(response) > 3800:
                response = response[:3800] + "\n\n... (truncated)"
            return response
        else:
            logger.error(f"Claude CLI error: {result.stderr}")
            return f"Claude CLI error: {result.stderr[:500]}"

    except subprocess.TimeoutExpired:
        return "Request timed out. The question might be too complex."
    except FileNotFoundError:
        return "Claude CLI not found. Make sure 'claude' is installed and in PATH."
    except Exception as e:
        logger.exception("Error calling Claude CLI")
        return f"Error: {str(e)}"


def generate_clarification_questions(original_question: str, history: list) -> tuple[str, bool]:
    """Generate clarification questions or determine readiness."""
    history_text = ""
    if history:
        history_text = "\n\nPrevious Q&A:\n"
        for i, (q, a) in enumerate(history, 1):
            history_text += f"{i}. Q: {q}\n   A: {a}\n"

    prompt = f"""You are helping clarify a task request before development.

Original request: {original_question}
{history_text}

If you have enough info, respond with "READY_TO_PROCEED" on the first line, then a brief summary.
If not, ask 1-3 specific clarification questions.

Use Slack mrkdwn format (*bold*, not **bold**).
"""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--no-session-persistence"],
            capture_output=True, text=True,
            cwd=str(config.PROJECT_ROOT), timeout=120,
        )
        if result.returncode == 0:
            response = result.stdout.strip()
            is_ready = response.startswith("READY_TO_PROCEED")
            if is_ready:
                response = response.replace("READY_TO_PROCEED", "").strip()
            return response, is_ready
        else:
            return "Error generating clarification questions.", False
    except Exception as e:
        return f"Error: {str(e)}", False


def format_messages(messages: list, bot_user_id: str) -> list[str]:
    lines = []
    for msg in messages:
        msg_text = re.sub(rf'<@{bot_user_id}>\s*', '', msg.get("text", "")).strip()
        if msg_text:
            role = "Bot" if msg.get("bot_id") else "User"
            lines.append(f"{role}: {msg_text}")
    return lines


def summarize_thread(messages: list[str]) -> str:
    conversation = "\n".join(messages)
    prompt = f"""Summarize this conversation in 2-3 sentences:
1. What the user asked
2. Key information in responses
3. Unresolved questions

Conversation:
{conversation}

Summary (same language as conversation):"""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--no-session-persistence"],
            capture_output=True, text=True,
            cwd=str(config.PROJECT_ROOT), timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "\n".join(messages[-3:])
    except Exception:
        return "\n".join(messages[-3:])


def cleanup_expired_cache():
    current_time = time.time()
    expired = [k for k, v in thread_summaries.items()
               if current_time - v.last_updated > config.CACHE_TTL_SECONDS]
    for key in expired:
        del thread_summaries[key]


def get_optimized_context(client, channel: str, thread_ts: str, bot_user_id: str) -> str:
    """Fetch thread context with caching and summarization."""
    try:
        cleanup_expired_cache()
        result = client.conversations_replies(channel=channel, ts=thread_ts, limit=50)
        messages = result.get("messages", [])
        if len(messages) <= 1:
            return ""

        prev_messages = messages[:-1]
        msg_count = len(prev_messages)
        cache_key = f"{channel}:{thread_ts}"
        formatted = format_messages(prev_messages, bot_user_id)

        if msg_count <= config.SUMMARY_THRESHOLD:
            return "Previous conversation:\n" + "\n".join(formatted)

        if cache_key in thread_summaries:
            cached = thread_summaries[cache_key]
            new_msg_count = msg_count - cached.message_count
            if new_msg_count <= config.MAX_RECENT_MESSAGES:
                recent = formatted[-new_msg_count:] if new_msg_count > 0 else []
                ctx = f"[Summary]\n{cached.summary}"
                if recent:
                    ctx += f"\n\n[Recent]\n" + "\n".join(recent)
                return ctx

        older = formatted[:-config.MAX_RECENT_MESSAGES]
        recent = formatted[-config.MAX_RECENT_MESSAGES:]
        summary = summarize_thread(older)

        thread_summaries[cache_key] = ThreadCache(
            summary=summary,
            message_count=msg_count - config.MAX_RECENT_MESSAGES,
        )

        return f"[Summary]\n{summary}\n\n[Recent]\n" + "\n".join(recent)
    except Exception as e:
        logger.error(f"Error fetching thread context: {e}")
        return ""


def add_mentions(user: str) -> str:
    """Build mention string for replies."""
    mentions = f"<@{user}>"
    if config.ALWAYS_MENTION_USER and user != config.ALWAYS_MENTION_USER:
        mentions += f" <@{config.ALWAYS_MENTION_USER}>"
    return mentions


def post_review_message(client, question: str, original_user: str,
                        original_channel: str, original_ts: str) -> tuple:
    """Post a review discussion to the review channel."""
    if not config.REVIEW_CHANNEL_ID:
        return None, None
    try:
        permalink = client.chat_getPermalink(
            channel=original_channel, message_ts=original_ts
        ).get("permalink", "")

        text = f"""*Review Request* (<@{original_user}>)

{question}

<{permalink}|Original message>

Let me look into this in detail!"""

        result = client.chat_postMessage(channel=config.REVIEW_CHANNEL_ID, text=text)
        review_ts = result["ts"]

        cache_key = f"{original_channel}:{original_ts}"
        review_threads[cache_key] = f"{config.REVIEW_CHANNEL_ID}:{review_ts}"
        return review_ts, permalink
    except Exception as e:
        logger.error(f"Error posting review message: {e}")
        return None, None


# --- ClickHouse Query Handler ---
def parse_alert_message(question: str) -> Optional[dict]:
    """Parse alert message format and extract parameters."""
    if not config.CLICKHOUSE_ENABLED:
        return None

    alert_pattern = r'"(\d{4}-\d{2}-\d{2}T[\d:]+\.\d+Z)","([^"]+)","([^"]+)",\d+,"([^"]+)"'
    match = re.search(alert_pattern, question)
    if match:
        timestamp_str, service_name, error_type, api_path = match.groups()
        return {"service_name": service_name, "timestamp": timestamp_str,
                "error_type": error_type, "api_path": api_path, "is_alert": True}

    if "Alert for" in question or "Time Range (UTC)" in question:
        if config.CLICKHOUSE_DEFAULT_SERVICE and config.CLICKHOUSE_DEFAULT_SERVICE in question:
            return {"service_name": config.CLICKHOUSE_DEFAULT_SERVICE, "is_alert": True, "partial": True}
    return None


def handle_clickhouse_query(question: str) -> Optional[str]:
    """Check if question is a ClickHouse query and return results."""
    if not config.CLICKHOUSE_ENABLED:
        return None

    q_lower = question.lower()

    # Check alerts
    alert_info = parse_alert_message(question)
    if alert_info and alert_info.get("is_alert"):
        service = alert_info.get("service_name", config.CLICKHOUSE_DEFAULT_SERVICE)
        try:
            result = query_clickhouse.query_http_500_errors(service, hours=1, limit=20)
            return f"\n*Alert Analysis ({service})*\nRecent 1h HTTP 500 errors:\n\n{result}"
        except Exception as e:
            return f"Alert analysis error: {str(e)}"

    patterns = {
        "500": ["500 error", "500 errors", "http 500"],
        "slow": ["slow request", "slow query", "slow requests"],
        "stats": ["stats", "statistics"],
        "trace": ["trace"],
        "services": ["service list", "services"],
        "alert": ["alert analysis", "analyze alert"],
    }

    for cmd, keywords in patterns.items():
        if any(kw in q_lower for kw in keywords):
            service = config.CLICKHOUSE_DEFAULT_SERVICE
            hours = 24
            hour_match = re.search(r'(\d+)\s*(hour|hr|h)', question, re.IGNORECASE)
            if hour_match:
                hours = int(hour_match.group(1))

            threshold = 1000
            threshold_match = re.search(r'(\d+)\s*(ms)', question)
            if threshold_match:
                threshold = int(threshold_match.group(1))

            trace_match = re.search(r'[a-f0-9]{32}', question)
            trace_id = trace_match.group(0) if trace_match else None

            try:
                if cmd == "500":
                    return query_clickhouse.query_http_500_errors(service, hours)
                elif cmd == "slow":
                    return query_clickhouse.query_slow_requests(service, hours, threshold)
                elif cmd == "stats":
                    return query_clickhouse.query_service_stats(service, hours)
                elif cmd == "trace" and trace_id:
                    return query_clickhouse.query_trace_by_id(trace_id)
                elif cmd == "services":
                    services = query_clickhouse.get_service_names()
                    return "\n*Available ServiceNames*\n" + "\n".join(f"- {s}" for s in services[:50])
                elif cmd == "alert":
                    result = query_clickhouse.query_http_500_errors(service, hours, limit=20)
                    return f"\n*Alert Analysis ({service})*\n{result}"
            except Exception as e:
                return f"ClickHouse query error: {str(e)}"

    return None


# --- Event Handlers ---

@app.event("app_mention")
def handle_mention(event, say, client):
    """Handle when bot is mentioned in any channel/thread."""
    user = event.get("user")
    text = event.get("text", "")
    channel = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")

    logger.info(f"Mention from <@{user}> in {channel}")

    bot_user_id = get_bot_user_id(client)
    question, response_style = detect_response_style(text, bot_user_id)

    if not question:
        say(text="Please ask a question after mentioning me!", channel=channel, thread_ts=thread_ts)
        return

    # === REVIEW MODE ===
    if response_style == "review" and config.REVIEW_CHANNEL_ID:
        review_ts, permalink = post_review_message(client, question, user, channel, thread_ts)
        if review_ts:
            say(
                text=f"<@{user}> I'll review this in detail at <#{config.REVIEW_CHANNEL_ID}>!",
                channel=channel, thread_ts=thread_ts,
            )
            try:
                client.reactions_add(channel=config.REVIEW_CHANNEL_ID, timestamp=review_ts, name="thinking_face")
            except Exception:
                pass

            context_note = f"\nOriginal question link: {permalink}"
            response = call_claude_code(question, context=context_note, response_style="detailed")

            try:
                client.reactions_remove(channel=config.REVIEW_CHANNEL_ID, timestamp=review_ts, name="thinking_face")
            except Exception:
                pass

            client.chat_postMessage(
                channel=config.REVIEW_CHANNEL_ID,
                text=f"{add_mentions(user)}\n{response}",
                thread_ts=review_ts,
            )
        else:
            say(text=f"<@{user}> Error creating review thread.", channel=channel, thread_ts=thread_ts)
        return

    # === TASK REQUEST MODE ===
    if response_style == "task_request" and config.REVIEW_CHANNEL_ID:
        cleanup_expired_task_requests()
        review_ts, permalink = post_review_message(client, question, user, channel, thread_ts)
        if not review_ts:
            say(text=f"<@{user}> Error creating task request thread.", channel=channel, thread_ts=thread_ts)
            return

        say(
            text=f"<@{user}> Task request received! I'll clarify details at <#{config.REVIEW_CHANNEL_ID}>.",
            channel=channel, thread_ts=thread_ts,
        )

        state_key = f"{config.REVIEW_CHANNEL_ID}:{review_ts}"
        task_requests[state_key] = TaskRequestState(
            original_question=question, clarification_history=[],
            original_user=user, original_channel=channel, original_ts=thread_ts,
        )

        try:
            client.reactions_add(channel=config.REVIEW_CHANNEL_ID, timestamp=review_ts, name="thinking_face")
        except Exception:
            pass

        clarification, is_ready = generate_clarification_questions(question, [])

        try:
            client.reactions_remove(channel=config.REVIEW_CHANNEL_ID, timestamp=review_ts, name="thinking_face")
        except Exception:
            pass

        mentions = add_mentions(user)
        if is_ready:
            client.chat_postMessage(
                channel=config.REVIEW_CHANNEL_ID,
                text=f"{mentions}\n\n{clarification}\n\nStarting work now!",
                thread_ts=review_ts,
            )
            if state_key in task_requests:
                del task_requests[state_key]
        else:
            client.chat_postMessage(
                channel=config.REVIEW_CHANNEL_ID,
                text=f"{mentions}\n\n{clarification}",
                thread_ts=review_ts,
            )
        return

    # === NORMAL MODE ===
    clickhouse_context = ""
    if config.CLICKHOUSE_ENABLED:
        analysis_keywords = ["analyze", "analysis", "why", "cause", "reason", "explain"]
        needs_analysis = any(kw in question.lower() for kw in analysis_keywords)

        ch_result = handle_clickhouse_query(question)
        if ch_result:
            if needs_analysis:
                clickhouse_context = f"\n--- ClickHouse Results ---\n{ch_result}\n--- End ---\n"
            else:
                say(text=f"<@{user}>\n{ch_result}", channel=channel, thread_ts=thread_ts)
                return

    # Add thinking reaction
    try:
        client.reactions_add(channel=channel, timestamp=event.get("ts"), name="thinking_face")
    except Exception:
        pass

    # Thread context
    thread_context = ""
    if event.get("thread_ts"):
        thread_context = get_optimized_context(client, channel, thread_ts, bot_user_id)

    if clickhouse_context:
        thread_context = clickhouse_context + "\n" + thread_context

    response = call_claude_code(question, context=thread_context, response_style=response_style)

    try:
        client.reactions_remove(channel=channel, timestamp=event.get("ts"), name="thinking_face")
    except Exception:
        pass

    if not response or is_error_response(response):
        say(text=f"<@{user}> Sorry, I failed to respond. Please try again later.", channel=channel, thread_ts=thread_ts)
        notify_error_to_owner(client, response or "Empty response", user, channel, question)
        return

    say(text=f"{add_mentions(user)}\n{response}", channel=channel, thread_ts=thread_ts)


@app.event("message")
def handle_message(event, say, client):
    """Handle DMs and review channel replies."""
    if event.get("bot_id") or event.get("subtype"):
        return

    channel = event.get("channel", "")
    text = event.get("text", "")

    # Skip bot mentions - handled by app_mention
    bot_user_id = get_bot_user_id(client)
    if f"<@{bot_user_id}>" in text:
        return

    thread_ts = event.get("thread_ts") or event.get("ts")
    user = event.get("user")

    if not text.strip():
        return

    # Task request clarification responses
    cleanup_expired_task_requests()
    state_key = f"{channel}:{thread_ts}"
    if state_key in task_requests and thread_ts != event.get("ts"):
        task_state = task_requests[state_key]

        try:
            client.reactions_add(channel=channel, timestamp=event.get("ts"), name="thinking_face")
        except Exception:
            pass

        # Get last bot question
        last_question = "(response to previous question)"
        try:
            replies = client.conversations_replies(channel=channel, ts=thread_ts, limit=10)
            for msg in reversed(replies.get("messages", [])[:-1]):
                if msg.get("bot_id"):
                    last_question = msg.get("text", "")[:200]
                    break
        except Exception:
            pass

        task_state.clarification_history.append((last_question, text.strip()))
        next_response, is_ready = generate_clarification_questions(
            task_state.original_question, task_state.clarification_history
        )

        try:
            client.reactions_remove(channel=channel, timestamp=event.get("ts"), name="thinking_face")
        except Exception:
            pass

        mentions = add_mentions(user)
        if is_ready:
            say(text=f"{mentions}\n\n{next_response}\n\nGot it! Starting work now!", channel=channel, thread_ts=thread_ts)
            if state_key in task_requests:
                del task_requests[state_key]
        else:
            say(text=f"{mentions}\n\n{next_response}", channel=channel, thread_ts=thread_ts)
        return

    # DMs only
    if not channel.startswith("D"):
        return

    logger.info(f"DM from <@{user}>: {text[:100]}...")

    try:
        client.reactions_add(channel=channel, timestamp=event.get("ts"), name="thinking_face")
    except Exception:
        pass

    response = call_claude_code(text)

    try:
        client.reactions_remove(channel=channel, timestamp=event.get("ts"), name="thinking_face")
    except Exception:
        pass

    say(text=response, channel=channel, thread_ts=thread_ts)


@app.event("reaction_added")
def handle_reaction(event, client):
    pass


def sync_slack_user_cache():
    try:
        import slack_user_cache
        if slack_user_cache.needs_sync():
            logger.info("Syncing Slack user cache...")
            stats = slack_user_cache.sync_from_slack(app.client)
            logger.info(f"Slack user cache synced: {stats}")
        else:
            logger.info("Slack user cache is up to date")
    except Exception as e:
        logger.warning(f"Failed to sync Slack user cache: {e}")


def main():
    logger.info(f"Starting Claude Slack Bot...")
    logger.info(f"Project root: {config.PROJECT_ROOT}")
    logger.info(f"Claude add-dir: {config.CLAUDE_ADD_DIR}")
    logger.info(f"ClickHouse: {'enabled' if config.CLICKHOUSE_ENABLED else 'disabled'}")
    logger.info(f"Review channel: {config.REVIEW_CHANNEL_ID or 'not set'}")

    sync_slack_user_cache()
    logger.info("Bot is ready! Mention me in any channel or send a DM.")

    while True:
        try:
            handler = SocketModeHandler(app, config.SLACK_APP_TOKEN)
            handler.start()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"SocketModeHandler crashed: {type(e).__name__}: {e}")
            logger.info("Restarting in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    main()
