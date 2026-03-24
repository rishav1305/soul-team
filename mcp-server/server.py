#!/usr/bin/env python3
"""
soul-team MCP Server — Team-lead interface for multi-agent coordination.

Part of the soul-team open-source multi-agent framework.
Exposes ClawTeam operations as MCP tools for Claude Code.

Run: python3 server.py   (stdio transport, used by Claude Code MCP integration)

Configuration (environment variables):
    SOUL_TEAM_NAME    — Team name (default: "soul-team")
    SOUL_AGENT_NAME   — Your agent identity (default: "team-lead")
    CLAWTEAM_BIN      — Path to clawteam binary (default: ~/.local/bin/clawteam)
    CLAWTEAM_DATA_DIR — Path to clawteam data dir (default: ~/.clawteam)
    SOUL_TEAM_CONFIG  — Path to native team config JSON (default: ~/.claude/teams/<team>/config.json)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Config ───────────────────────────────────────────────────────────────────
TEAM = os.environ.get("SOUL_TEAM_NAME", "soul-team")
SENDER = os.environ.get("SOUL_AGENT_NAME", "team-lead")
CLAWTEAM = os.environ.get("CLAWTEAM_BIN", str(Path.home() / ".local" / "bin" / "clawteam"))
CLAWTEAM_DATA = Path(os.environ.get("CLAWTEAM_DATA_DIR", str(Path.home() / ".clawteam")))
NATIVE_INBOX_DIR = Path.home() / ".claude" / "teams" / TEAM / "inboxes"
NATIVE_INBOX_LEAD = NATIVE_INBOX_DIR / f"{SENDER}.json"

mcp = FastMCP(
    "soul-team",
    instructions=(
        "Tools for managing a soul-team multi-agent system. "
        "Use these to send messages, check inboxes, manage tasks, "
        "view team status, and peek at agent activity."
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_clawteam(*args):
    """Run clawteam CLI. Returns (returncode, stdout, stderr)."""
    cmd = [CLAWTEAM] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.returncode, r.stdout, r.stderr


def run_clawteam_json(*args):
    """Run clawteam with --json. Returns (data, error)."""
    cmd = [CLAWTEAM, "--json"] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return None, r.stderr.strip() or f"clawteam exit {r.returncode}"
    try:
        return json.loads(r.stdout), None
    except json.JSONDecodeError:
        return None, f"JSON parse error: {r.stdout[:300]}"


def priority_key(priority):
    return {"P1": "urgent", "P2": "normal", "P3": "low"}.get(priority, "normal")


def append_native_inbox(from_agent, text):
    """Mirror a message to the native team-lead inbox."""
    NATIVE_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    msgs = []
    if NATIVE_INBOX_LEAD.exists():
        try:
            msgs = json.loads(NATIVE_INBOX_LEAD.read_text())
        except (json.JSONDecodeError, IOError):
            msgs = []
    msgs.append({
        "from": from_agent,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
    })
    NATIVE_INBOX_LEAD.write_text(json.dumps(msgs, indent=2))


def _get_team_config_path():
    """Return the path to the native team config JSON."""
    env_path = os.environ.get("SOUL_TEAM_CONFIG")
    if env_path:
        return Path(env_path)
    return Path.home() / ".claude" / "teams" / TEAM / "config.json"


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def soul_send_message(to: str, message: str, priority: str = "P2") -> str:
    """
    Send a message to a soul-team agent.

    Args:
        to: Recipient agent name
        message: Message text to send
        priority: P1 (urgent), P2 (normal), P3 (low)
    """
    key = priority_key(priority)
    rc, out, err = run_clawteam(
        "inbox", "send", TEAM, to, message,
        "--from", SENDER,
        "--key", key,
    )
    if rc != 0:
        return f"ERROR: {err.strip() or 'clawteam send failed'}"

    result = out.strip() or f"Message sent to {to} [{priority}]"

    if to == SENDER:
        append_native_inbox(SENDER, message)
        result += f"\n(mirrored to native {SENDER} inbox)"

    return result


@mcp.tool()
def soul_check_inbox(unread_only: bool = True) -> str:
    """
    Check your inbox for messages from agents.

    Args:
        unread_only: If True, show only unread messages
    """
    # Try clawteam first
    data, err = run_clawteam_json("inbox", "peek", TEAM, "--agent", SENDER)

    msgs = []
    source = "clawteam"

    if data is not None:
        msgs = data if isinstance(data, list) else data.get("messages", [])
    else:
        # Fallback to native inbox
        if NATIVE_INBOX_LEAD.exists():
            try:
                msgs = json.loads(NATIVE_INBOX_LEAD.read_text())
                source = "native"
            except (json.JSONDecodeError, IOError):
                msgs = []

    if unread_only:
        msgs = [m for m in msgs if not m.get("read", False)]

    if not msgs:
        return "Inbox empty." if not unread_only else "No unread messages."

    lines = [f"Inbox ({source}, {len(msgs)} messages):"]
    lines.append("-" * 60)
    for i, m in enumerate(msgs, 1):
        ts = m.get("timestamp", "")[:19].replace("T", " ")
        sender = m.get("from", "?")
        key = m.get("key", "normal")
        pri = {"urgent": "P1", "normal": "P2", "low": "P3"}.get(key, key)
        text = m.get("text", m.get("content", ""))
        read_mark = "" if m.get("read") else "[UNREAD] "
        lines.append(f"{i}. {read_mark}From: {sender} | {pri} | {ts}")
        lines.append(f"   {text}")
    return "\n".join(lines)


@mcp.tool()
def soul_broadcast(message: str) -> str:
    """
    Broadcast a message to all soul-team agents.

    Args:
        message: Message to send to all agents
    """
    args = ["inbox", "broadcast", TEAM, message]
    if SENDER == "team-lead":
        args.extend(["--key", "urgent"])
    rc, out, err = run_clawteam(*args)
    if rc != 0:
        return f"ERROR: {err.strip() or 'broadcast failed'}"
    return out.strip() or "Broadcast sent to all agents."


@mcp.tool()
def soul_task_create(title: str, assign: str = None, blocked_by: str = None) -> str:
    """
    Create a new task in the team task board.

    Args:
        title: Task subject/title
        assign: Agent to assign to (optional)
        blocked_by: Comma-separated task IDs that block this task (optional)
    """
    args = ["task", "create", TEAM, title]
    if assign:
        args += ["--owner", assign]
    if blocked_by:
        args += ["--blocked-by", blocked_by]

    rc, out, err = run_clawteam(*args)
    if rc != 0:
        return f"ERROR: {err.strip() or 'task create failed'}"
    return out.strip() or f"Task created: {title}"


@mcp.tool()
def soul_task_list(status: str = None, owner: str = None) -> str:
    """
    List tasks on the team task board.

    Args:
        status: Filter by status (pending, in_progress, completed, blocked)
        owner: Filter by owner agent name
    """
    args = ["task", "list", TEAM]
    if status:
        args += ["--status", status]
    if owner:
        args += ["--owner", owner]

    rc, out, err = run_clawteam(*args)
    if rc != 0:
        return f"ERROR: {err.strip() or 'task list failed'}"
    return out.strip() or "No tasks found."


@mcp.tool()
def soul_task_update(task_id: str, status: str) -> str:
    """
    Update a task's status on the team task board.

    Args:
        task_id: Task ID to update
        status: New status (pending, in_progress, completed, blocked)
    """
    rc, out, err = run_clawteam(
        "task", "update", TEAM, task_id,
        "--status", status,
    )
    if rc != 0:
        return f"ERROR: {err.strip() or 'task update failed'}"
    return out.strip() or f"Task {task_id} updated to {status}."


@mcp.tool()
def soul_team_status() -> str:
    """
    Show team member status, tmux panes, and heartbeats.
    """
    # Use clawteam's own team status for authoritative member list
    data, err = run_clawteam_json("team", "status", TEAM)
    if err or data is None:
        return f"ERROR reading team status: {err}"

    members = data.get("members", [])
    lead_id = data.get("leadAgentId", "?")
    lines = [
        f"Team:  {data.get('name', TEAM)}",
        f"Lead:  {lead_id}",
        f"Members: {len(members)}",
        "",
        f"{'NAME':<14} {'TYPE':<10} {'AGENT_ID':<16} JOINED",
        "-" * 60,
    ]
    for m in members:
        name = m.get("name", "?")
        atype = m.get("agentType", "?")
        aid = m.get("agentId", "?")[:12]
        joined = m.get("joinedAt", "")[:10]
        lead_mark = " (lead)" if m.get("agentId") == lead_id else ""
        lines.append(f"{name:<14} {atype:<10} {aid:<16} {joined}{lead_mark}")

    # Tmux pane info from native config
    native_cfg = _get_team_config_path()
    if native_cfg.exists():
        try:
            cfg = json.loads(native_cfg.read_text())
            pane_map = {m.get("name"): m.get("tmuxPaneId", "") for m in cfg.get("members", [])}
            active_panes = [(n, p) for n, p in pane_map.items() if p]
            if active_panes:
                lines.append(f"\nTmux panes ({len(active_panes)}):")
                for name, pane in sorted(active_panes):
                    lines.append(f"  {name:<14} {pane}")
        except (json.JSONDecodeError, IOError):
            pass

    # Heartbeats
    hb_dir = CLAWTEAM_DATA / "teams" / TEAM / "heartbeat"
    if hb_dir.exists():
        hb_files = list(hb_dir.glob("*.json"))
        lines.append(f"\nHeartbeats: {len(hb_files)} file(s)")
        for hf in sorted(hb_files)[:10]:
            try:
                hb = json.loads(hf.read_text())
                ts = hb.get("timestamp", "")[:19].replace("T", " ")
                agent = hb.get("agent", hf.stem)
                lines.append(f"  {agent:<14} last seen {ts}")
            except (json.JSONDecodeError, IOError):
                pass
    else:
        lines.append("\nHeartbeats: none")

    return "\n".join(lines)


@mcp.tool()
def soul_peek_agent(agent: str, lines: int = 30) -> str:
    """
    Capture recent output from an agent's tmux pane.

    Args:
        agent: Agent name
        lines: Number of lines to capture (default 30)
    """
    # Use native config which has tmuxPaneId populated
    config_path = _get_team_config_path()
    if not config_path.exists():
        return "ERROR: Native team config not found (team launch config missing)."

    try:
        cfg = json.loads(config_path.read_text())
    except (json.JSONDecodeError, IOError) as e:
        return f"ERROR reading config: {e}"

    pane_id = None
    for m in cfg.get("members", []):
        if m.get("name") == agent:
            pane_id = m.get("tmuxPaneId", "")
            break

    if pane_id is None:
        return f"Agent '{agent}' not found in team."
    if not pane_id:
        return f"No tmux pane registered for {agent} (agent may not be running)."

    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"tmux capture failed for pane {pane_id}: {result.stderr.strip()}"

    output = result.stdout.rstrip()
    if not output:
        return f"(pane {pane_id} for {agent} is empty)"

    return f"--- {agent} (pane {pane_id}) ---\n{output}"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
