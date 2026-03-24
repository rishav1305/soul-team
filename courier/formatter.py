"""Soul Courier — message formatting for tmux pane injection.

Formats incoming messages into human-readable text blocks suitable for
pasting into agent tmux panes. Supports direct messages, broadcasts,
group discussions, status updates, P1 interrupts, and batch summaries.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger("soul-courier.formatter")

TEAM_NAME = os.environ.get("SOUL_TEAM_NAME", "soul-team")


class MessageFormatter:
    @staticmethod
    def _read(msg_file: Path) -> dict:
        try:
            return json.loads(msg_file.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot read message %s", msg_file)
            return {}

    @classmethod
    def format(cls, msg_file: Path, agent: str, is_crunched: bool = False) -> str:
        data = cls._read(msg_file)
        if not data:
            return ""

        msg_type = data.get("type", "message")
        from_user = data.get("from", "unknown")
        content = data.get("content", "")
        action = data.get("action", "")
        thread_id = data.get("thread_id", "")

        if agent == "team-lead":
            return cls._format_team_lead(data)

        if msg_type == "broadcast":
            return (
                f"[BROADCAST] From: {from_user}\n"
                f"---\n{content}\n---\n"
                f"Respond to CEO inbox via: clawteam inbox send {TEAM_NAME} "
                f"team-lead \"your response\" --from {agent}"
            )

        if msg_type == "group-discussion":
            ts = int(time.time())
            msg_count = data.get("message_count", "?")
            base = (
                f"[DISCUSSION: {thread_id}] From: {from_user} (message {msg_count})\n"
                f"---\n{content}\n---\n"
                f"Respond by writing to discussions/{thread_id}/ "
                f"with filename: {ts}-{agent}.json\n"
                f"Keep it under 200 words. Reference peers by name."
            )
            if is_crunched and thread_id:
                summary = cls._build_thread_summary(thread_id)
                if summary:
                    base = f"Thread summary (context was compressed):\n{summary}\n{base}"
            return base

        if msg_type == "status":
            if action and action != "null":
                return f"[{from_user}] {action}: {content}"
            return f"[{from_user}] {content}"

        return (
            f"[INBOX] From: {from_user} | Type: {msg_type}\n"
            f"---\n{content}\n---\n"
            f"Respond by writing to {from_user}'s inbox via: "
            f"clawteam inbox send {TEAM_NAME} {from_user} "
            f"\"your response\" --from {agent}"
        )

    @classmethod
    def _format_team_lead(cls, data: dict) -> str:
        """Format messages for team-lead pane with visual prefix tags."""
        from_user = data.get("from", "unknown")
        content = data.get("content", "")
        action = data.get("action", "")
        action_required = data.get("action_required", False)
        action_type = data.get("action_type", "action")

        # System notifications (courier, guardian, router)
        if from_user in ("courier", "guardian", "router"):
            if action and action != "null":
                return f"\u2699 [{from_user}] {action}: {content}"
            return f"\u2699 [{from_user}] {content}"

        # Action items
        if action_required:
            if action_type == "decide":
                return f"\u2753 DECIDE [{from_user}] {content}"
            return f"\u26a1 ACTION [{from_user}] {content}"

        # FYI status (default)
        if action and action != "null":
            return f"\u2713 [{from_user}] {action}: {content}"
        return f"\u2713 [{from_user}] {content}"

    @classmethod
    def format_p1(cls, msg_file: Path, agent: str) -> str:
        data = cls._read(msg_file)
        from_user = data.get("from", "unknown")
        content = data.get("content", "")
        if from_user in ("unknown", "agent", ""):
            from_user = "team-lead"

        return (
            f"[P1 INTERRUPT from {from_user}]\n\n"
            f"STEP 1: Save your interrupted state to memory NOW.\n"
            f"Write a project memory titled \"interrupted-state\" containing:\n"
            f"- What task/routine step you were executing\n"
            f"- What you had completed so far\n"
            f"- What steps remain\n\n"
            f"STEP 2: Handle this message:\n"
            f"---\n{content}\n---\n"
            f"Respond via: clawteam inbox send {TEAM_NAME} {from_user} "
            f"\"your response\" --from {agent}\n\n"
            f"STEP 3: After handling, check your memory for \"interrupted-state\". "
            f"If found:\n"
            f"- Read it to recall where you left off\n"
            f"- Delete the memory (it is consumed)\n"
            f"- Continue from where you stopped"
        )

    @classmethod
    def format_batch(cls, thread_id: str, files: list[Path], agent: str) -> str:
        ts = int(time.time())
        count = len(files)
        lines = [f"[DISCUSSION: {thread_id}] {count} new messages since your last response:"]
        for f in files:
            data = cls._read(f)
            from_user = data.get("from", "unknown")
            excerpt = data.get("content", "")[:120]
            lines.append(f'- {from_user}: "{excerpt}"')
        lines.append("---")
        lines.append(
            f"Respond to the thread or say \"acknowledged\" if nothing to add.\n"
            f"Write to discussions/{thread_id}/{ts}-{agent}.json"
        )
        return "\n".join(lines)

    @staticmethod
    def _build_thread_summary(thread_id: str) -> str:
        team_name = os.environ.get("SOUL_TEAM_NAME", "soul-team")
        disc_dir = Path.home() / ".clawteam" / "teams" / team_name / "discussions" / thread_id
        if not disc_dir.is_dir():
            return ""
        lines = []
        for f in sorted(disc_dir.glob("*.json")):
            if f.name == "state.json":
                continue
            try:
                data = json.loads(f.read_text())
                from_user = data.get("from", "unknown")
                excerpt = data.get("content", "")[:100]
                lines.append(f'- {from_user}: "{excerpt}"')
            except (json.JSONDecodeError, OSError):
                continue
        return "\n".join(lines)
