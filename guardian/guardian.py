#!/usr/bin/env python3
"""
guardian.py -- System watchdog for soul-team multi-agent orchestration.

Part of the soul-team open-source project. Monitors a tmux-based agent team,
auto-restarts crashed agents, tracks token spend, enforces daily cost caps,
and protects the host machine from thermal/memory/CPU overload.

Usage:
    python3 guardian.py              # Run as daemon (systemd)
    python3 guardian.py --check      # Dry-run: print state, no actions
    python3 guardian.py --once       # Single cycle then exit

Environment:
    SOUL_GUARDIAN_DB       Path to SQLite DB (default: ~/.soul/guardian.db)
    SOUL_TEAM_NAME         tmux session name (default: soul-team)
    SOUL_GUARDIAN_LOG      Path to log file (default: ~/.soul/guardian.log)
    SOUL_TEAM_CONFIG       Path to team config JSON (default: ~/.soul/team-config.json)
    SOUL_TEAM_TOML         Path to team TOML (default: ~/.soul/soul-team.toml)
    SOUL_BRIDGE_SCRIPT     Path to bridge daemon script (optional)
    SOUL_MSG_BIN           Path to messaging binary (optional)
    SOUL_CRITICAL_AGENTS   Comma-separated agent names that must never be paused (default: empty)
    SOUL_MACHINES_JSON     Path to JSON file mapping machine names to SSH targets (optional)
"""

import argparse
import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# -- Constants ----------------------------------------------------------------

VERSION = "2.0.0"

# System limits
TEMP_LIMIT_C = 80          # degrees C -- kill newest agent above this
CPU_WARN_PCT = 95          # percent -- log warning above this
MEM_MIN_MB = 1500          # MB -- kill heaviest agent if free < this

# Loop intervals
MAIN_INTERVAL_S = 30       # seconds between main guard cycles
TOKEN_INTERVAL_S = 60      # seconds between token scans
SPEND_INTERVAL_S = 60      # seconds between spend checks

# Auto-restart
MAX_RESTARTS_PER_HOUR = 3

# Auto-compact
COMPACT_COOLDOWN_S = 300   # 5 minutes
MSG_COUNT_COMPACT_THRESHOLD = 200

# Spend limits
SPEND_ALERT_USD = 48.0     # 80% of $60 cap
SPEND_CAP_USD = 60.0       # Hard daily cap

# Token cost rates (per million tokens)
COST_RATES = {
    "opus": {
        "input": 15.0 / 1_000_000,
        "output": 75.0 / 1_000_000,
        "cache_read": 1.50 / 1_000_000,
    },
    "sonnet": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    },
}

# Agents that must NEVER be paused (configurable via SOUL_CRITICAL_AGENTS env var)
_critical_env = os.environ.get("SOUL_CRITICAL_AGENTS", "")
CRITICAL_AGENTS: set[str] = {
    a.strip() for a in _critical_env.split(",") if a.strip()
}

# Shell prompt patterns -- agent has crashed out of Claude TUI
SHELL_PROMPT_RE = re.compile(r"(?m)^.*[\$\#]\s*$")
BARE_PROMPT_RE = re.compile(r"(?m)^\s*(bash-\d+[\$\#]|sh-\d+[\$\#]|\$\s*$|#\s*$)")

# Context / compact trigger patterns
COMPACT_TRIGGER_RE = re.compile(
    r"context.*(limit|full|running out|compact)", re.IGNORECASE
)

# Auto-continue: safe prompts to answer Y
SAFE_AUTO_APPROVE_RE = re.compile(
    r"(\[Y/n\]|Do you want to proceed|Allow .* to make changes|Press Enter to continue)",
    re.IGNORECASE,
)

# NEVER auto-answer -- dangerous confirmations
NEVER_AUTO_APPROVE_RE = re.compile(
    r"(Which model|Enter.*password|Delete.*\?|Force push|Drop.*table)",
    re.IGNORECASE,
)

# Token patterns Claude Code may print (heuristic -- parse what's available)
TOKEN_PATTERNS = [
    # "Tokens: 12,345 input / 4,567 output"
    re.compile(
        r"[Tt]okens?:\s*([\d,]+)\s+input\s*/\s*([\d,]+)\s+output",
        re.IGNORECASE,
    ),
    # "Context: 45%" or "Context window: 45%"
    re.compile(r"[Cc]ontext(?:\s+window)?:\s*(\d+(?:\.\d+)?)\s*%"),
    # "Cost: $0.42" or similar
    re.compile(r"[Cc]ost:\s*\$?([\d.]+)"),
]

# -- Configurable Paths -------------------------------------------------------

HOME = Path.home()

DB_PATH = Path(
    os.environ.get("SOUL_GUARDIAN_DB", str(HOME / ".soul" / "guardian.db"))
)
LOG_PATH = Path(
    os.environ.get("SOUL_GUARDIAN_LOG", str(HOME / ".soul" / "guardian.log"))
)
TEAM_NAME = os.environ.get("SOUL_TEAM_NAME", "soul-team")
TEAMS_CONFIG = Path(
    os.environ.get("SOUL_TEAM_CONFIG", str(HOME / ".soul" / "team-config.json"))
)
SOUL_TEAM_TOML = Path(
    os.environ.get("SOUL_TEAM_TOML", str(HOME / ".soul" / "soul-team.toml"))
)
BRIDGE_SCRIPT = Path(
    os.environ.get("SOUL_BRIDGE_SCRIPT", str(HOME / ".soul" / "soul-bridge.py"))
)
SOUL_MSG = Path(
    os.environ.get("SOUL_MSG_BIN", "/usr/local/bin/soul-msg")
)

# Machine config: JSON file mapping machine aliases to SSH targets.
# Example: {"remote-server": {"ssh_target": "user@host", "ssh_args": ["-p", "22"]}}
# Agents assigned to a machine alias will be launched via SSH to that target.
MACHINES_JSON = Path(
    os.environ.get("SOUL_MACHINES_JSON", str(HOME / ".soul" / "machines.json"))
)

_machines_config: dict[str, dict] = {}


def load_machines_config() -> dict[str, dict]:
    """Load machine alias -> SSH target mapping from JSON config file."""
    global _machines_config
    try:
        data = json.loads(MACHINES_JSON.read_text())
        if isinstance(data, dict):
            _machines_config = data
    except (OSError, json.JSONDecodeError):
        _machines_config = {}
    return _machines_config


# -- Logging ------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()[:19]


def now_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def log(msg: str, level: str = "INFO") -> None:
    """Write to stdout (systemd captures it) and to log file."""
    ts = now_iso()
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Never crash because of logging


def warn(msg: str) -> None:
    log(msg, "WARN")


def err(msg: str) -> None:
    log(msg, "ERROR")


# -- Database -----------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY,
            agent TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER,
            cost_usd REAL,
            context_pct REAL
        );

        CREATE TABLE IF NOT EXISTS daily_spend (
            date TEXT NOT NULL,
            agent TEXT NOT NULL,
            total_cost REAL,
            total_input INTEGER,
            total_output INTEGER,
            PRIMARY KEY (date, agent)
        );

        CREATE TABLE IF NOT EXISTS self_heal_events (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trigger TEXT NOT NULL,
            details TEXT
        );
    """)
    conn.commit()


def db_log_heal(conn: sqlite3.Connection, agent: str, event_type: str,
                trigger: str, details: str = "") -> None:
    conn.execute(
        "INSERT INTO self_heal_events (timestamp, agent, event_type, trigger, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (now_iso(), agent, event_type, trigger, details),
    )
    conn.commit()


def db_upsert_token_usage(conn: sqlite3.Connection, agent: str,
                          input_tok: int, output_tok: int,
                          cache_tok: int, cost: float, ctx_pct: float) -> None:
    conn.execute(
        "INSERT INTO token_usage "
        "(agent, timestamp, input_tokens, output_tokens, cache_read_tokens, cost_usd, context_pct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent, now_iso(), input_tok, output_tok, cache_tok, cost, ctx_pct),
    )
    today = now_date()
    conn.execute(
        """INSERT INTO daily_spend (date, agent, total_cost, total_input, total_output)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(date, agent) DO UPDATE SET
               total_cost = total_cost + excluded.total_cost,
               total_input = total_input + excluded.total_input,
               total_output = total_output + excluded.total_output""",
        (today, agent, cost, input_tok, output_tok),
    )
    conn.commit()


def db_today_total_spend(conn: sqlite3.Connection) -> float:
    today = now_date()
    row = conn.execute(
        "SELECT COALESCE(SUM(total_cost), 0) FROM daily_spend WHERE date = ?",
        (today,),
    ).fetchone()
    return row[0] if row else 0.0


# -- Config Loaders -----------------------------------------------------------

def load_agent_models() -> dict[str, str]:
    """Load agent -> model mapping from soul-team.toml."""
    models: dict[str, str] = {}
    try:
        content = SOUL_TEAM_TOML.read_text()
        # Simple TOML parser for [[agents]] sections (avoid toml dep)
        current_name = None
        current_model = None
        for line in content.splitlines():
            line = line.strip()
            if line == "[[agents]]":
                if current_name and current_model:
                    models[current_name] = current_model
                current_name = None
                current_model = None
            elif line.startswith("name ="):
                current_name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("model ="):
                current_model = line.split("=", 1)[1].strip().strip('"')
        if current_name and current_model:
            models[current_name] = current_model
    except OSError:
        pass
    return models


def load_team_config() -> list[dict]:
    """Load members with tmux pane IDs from native teams config."""
    try:
        data = json.loads(TEAMS_CONFIG.read_text())
        return data.get("members", [])
    except (OSError, json.JSONDecodeError):
        return []


def build_agent_pane_map() -> dict[str, str]:
    """Return {agent_name: pane_id} from native config, fallback to tmux titles."""
    pane_map: dict[str, str] = {}

    # Primary: native config (most accurate -- launcher writes it)
    members = load_team_config()
    for m in members:
        name = m.get("name", "")
        pane_id = m.get("tmuxPaneId", "")
        if name and pane_id and name != "team-lead":
            pane_map[name] = pane_id

    if pane_map:
        return pane_map

    # Fallback: scan tmux pane titles
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", TEAM_NAME,
             "-F", "#{pane_id} #{pane_title}"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                pane_id, title = parts
                name = title.strip().lstrip("\u2733 \u2810\u28f7").strip()
                if name:
                    pane_map[name] = pane_id
    except (subprocess.SubprocessError, OSError):
        pass

    return pane_map


# -- Agent State --------------------------------------------------------------

class AgentState:
    """Per-agent mutable state."""

    def __init__(self, name: str, pane_id: str, model: str, machine: str):
        self.name = name
        self.pane_id = pane_id
        self.model = model
        self.machine = machine
        self.last_output_hash = ""
        self.last_compact_ts = 0.0
        self.msg_count = 0
        self.status = "active"  # active | idle | stuck | crashed | unreachable
        self.restart_timestamps: list[float] = []  # last N restart times
        self.spend_alert_sent_today = False
        self.spend_date = ""

    def __repr__(self) -> str:
        return (
            f"AgentState(name={self.name!r}, pane={self.pane_id!r}, "
            f"model={self.model!r}, status={self.status!r})"
        )


# -- tmux Interaction ---------------------------------------------------------

def capture_pane(pane_id: str, lines: int = 50) -> str:
    """Capture last N lines of a tmux pane. Returns empty string on failure."""
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def send_keys(pane_id: str, keys: str) -> bool:
    """Send key sequence to a tmux pane. Returns True on success."""
    try:
        r = subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, keys, ""],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def send_enter(pane_id: str) -> bool:
    try:
        r = subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "", "Enter"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def pane_last_line(output: str) -> str:
    """Return the last non-empty line of captured pane output."""
    lines = [l for l in output.splitlines() if l.strip()]
    return lines[-1] if lines else ""


def pane_hash(output: str) -> str:
    return hashlib.md5(output.encode()).hexdigest()


def pane_is_shell_prompt(last_line: str) -> bool:
    """Heuristic: is this line a shell prompt (agent crashed out of Claude)?"""
    return bool(
        SHELL_PROMPT_RE.search(last_line) or
        BARE_PROMPT_RE.search(last_line) or
        re.search(r"@[\w-]+:[~\w/].*[\$\#]\s*$", last_line)
    )


# -- System Health ------------------------------------------------------------

def read_temp_celsius() -> int:
    """Read CPU temp from sysfs. Returns 0 on failure."""
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return int(raw) // 1000
    except (OSError, ValueError):
        return 0


def read_mem_free_mb() -> int:
    """Read MemAvailable from /proc/meminfo. Returns 99999 on failure."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                kb = int(line.split()[1])
                return kb // 1024
    except (OSError, ValueError):
        pass
    return 99999


def read_cpu_pct() -> float:
    """Get CPU usage via /proc/stat (two samples, 0.2s apart)."""
    def read_stat():
        line = Path("/proc/stat").read_text().splitlines()[0]
        vals = list(map(int, line.split()[1:]))
        idle = vals[3]
        total = sum(vals)
        return idle, total

    try:
        i1, t1 = read_stat()
        time.sleep(0.2)
        i2, t2 = read_stat()
        dt = t2 - t1
        if dt == 0:
            return 0.0
        return 100.0 * (1.0 - (i2 - i1) / dt)
    except (OSError, ValueError, IndexError):
        return 0.0


def find_heaviest_claude_pid() -> tuple[int, str]:
    """Return (pid, agent_name) of heaviest Claude agent by RSS."""
    try:
        r = subprocess.run(
            ["ps", "-eo", "pid,rss,args", "--sort=-rss"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "claude" in line and "--agent" in line:
                parts = line.split()
                pid = int(parts[0])
                m = re.search(r"--agent[- ](\w+)", line)
                name = m.group(1) if m else "unknown"
                return pid, name
    except (subprocess.SubprocessError, OSError, ValueError):
        pass
    return 0, ""


def find_newest_claude_pid() -> tuple[int, str]:
    """Return (pid, agent_name) of newest Claude agent by PID (highest PID = newest)."""
    try:
        r = subprocess.run(
            ["pgrep", "-af", "claude.*--agent"],
            capture_output=True, text=True, timeout=5,
        )
        candidates = []
        for line in r.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            m = re.search(r"--agent[- ](\w+)", line)
            name = m.group(1) if m else "unknown"
            candidates.append((pid, name))
        if candidates:
            return max(candidates, key=lambda x: x[0])
    except (subprocess.SubprocessError, OSError):
        pass
    return 0, ""


def kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


# -- Notifications ------------------------------------------------------------

def notify_ceo(message: str) -> bool:
    """Send message to team-lead via soul-msg. Best-effort."""
    if not SOUL_MSG.exists():
        return False
    try:
        r = subprocess.run(
            [str(SOUL_MSG), "send", "team-lead", message, "--priority", "P2"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


# -- Agent Launch Command -----------------------------------------------------

def build_launch_cmd(agent_name: str, model: str, machine: str) -> list[str] | None:
    """
    Build the tmux send-keys command to re-launch a claude agent in its pane.
    Mirrors what the launcher script does.

    For remote machines, reads SSH target from the machines config file
    (SOUL_MACHINES_JSON). For local agents, optionally wraps with systemd-run
    into a cgroup slice.
    """
    claude_bin = str(HOME / ".local" / "share" / "claude" / "claude")
    # Find actual versioned binary
    versions_dir = HOME / ".local" / "share" / "claude" / "versions"
    if versions_dir.is_dir():
        versioned = list(versions_dir.glob("*"))
        if versioned:
            claude_bin = str(sorted(versioned)[-1])  # latest version

    # Map "sonnet"/"opus" to model string
    model_map = {
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
    }
    model_str = model_map.get(model, model)

    base_cmd = (
        f"cd {HOME} && "
        f"env CLAUDECODE=1 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 "
        f"{claude_bin} "
        f"--agent-id {agent_name}@{TEAM_NAME} "
        f"--agent-name {agent_name} "
        f"--team-name {TEAM_NAME} "
        f"--agent-type {agent_name} "
        f"--dangerously-skip-permissions "
        f"--model {model_str}"
    )

    # Check if this machine is a remote target from config
    machine_cfg = _machines_config.get(machine, {})
    ssh_target = machine_cfg.get("ssh_target", "")

    if ssh_target:
        # Re-launch via SSH to remote machine
        ssh_args = machine_cfg.get("ssh_args", [])
        return ["ssh"] + ssh_args + [ssh_target, base_cmd]

    # Local -- wrap with systemd-run into cgroup slice (if available)
    cgroup_cmd = (
        f"systemd-run --user --scope --slice=soul-agents.slice "
        f"-- {base_cmd}"
    )
    return ["bash", "-c", cgroup_cmd]


# -- Auto-restart -------------------------------------------------------------

def restart_count_last_hour(state: AgentState) -> int:
    cutoff = time.time() - 3600
    state.restart_timestamps = [t for t in state.restart_timestamps if t > cutoff]
    return len(state.restart_timestamps)


def maybe_restart_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Check if this agent's pane is showing a shell prompt (crashed out of Claude).
    If so, re-launch up to MAX_RESTARTS_PER_HOUR per hour.
    Returns True if restart was triggered.
    """
    output = capture_pane(state.pane_id, lines=10)
    last = pane_last_line(output)

    if not pane_is_shell_prompt(last):
        return False

    # Check cooldown
    count = restart_count_last_hour(state)
    if count >= MAX_RESTARTS_PER_HOUR:
        warn(
            f"[{state.name}] Shell prompt detected but restart limit "
            f"({MAX_RESTARTS_PER_HOUR}/hr) reached -- skipping"
        )
        return False

    last_trunc = repr(last)[:80]
    log(
        f"[{state.name}] Shell prompt detected (last line: {last_trunc}). "
        f"Restart {count + 1}/{MAX_RESTARTS_PER_HOUR} this hour."
    )

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would restart now")
        return False

    launch_cmd = build_launch_cmd(state.name, state.model, state.machine)
    if not launch_cmd:
        err(f"[{state.name}] Could not build launch command -- skipping restart")
        return False

    # Send the launch command as keys into the pane
    cmd_str = subprocess.list2cmdline(launch_cmd)
    success = send_keys(state.pane_id, cmd_str)
    if success:
        send_enter(state.pane_id)

    if success:
        state.restart_timestamps.append(time.time())
        state.status = "active"
        db_log_heal(
            conn, state.name, "restart", "shell_prompt",
            f"last_line={last!r:.80} restart_count={count + 1}"
        )
        log(f"[{state.name}] Restarted (cmd sent to pane {state.pane_id})")
        # Only notify CEO when restart limit is hit (noise reduction)
        if count + 1 >= MAX_RESTARTS_PER_HOUR:
            notify_ceo(
                f"[guardian] {state.name} hit restart limit "
                f"({MAX_RESTARTS_PER_HOUR}/{MAX_RESTARTS_PER_HOUR} this hour)"
            )
        return True
    else:
        err(f"[{state.name}] send-keys failed for restart")
        return False


# -- Auto-compact -------------------------------------------------------------

def maybe_compact_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Send /compact if context warning detected or msg_count threshold exceeded.
    Respects per-agent cooldown.
    """
    now = time.time()
    if now - state.last_compact_ts < COMPACT_COOLDOWN_S:
        return False

    output = capture_pane(state.pane_id, lines=50)
    trigger = None

    if COMPACT_TRIGGER_RE.search(output):
        trigger = "context_warning"
    elif state.msg_count > MSG_COUNT_COMPACT_THRESHOLD:
        trigger = f"msg_count={state.msg_count}"

    if not trigger:
        return False

    log(f"[{state.name}] Auto-compact triggered ({trigger})")

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would send /compact")
        return False

    send_keys(state.pane_id, "/compact")
    send_enter(state.pane_id)
    state.last_compact_ts = now
    db_log_heal(conn, state.name, "compact", trigger)
    return True


# -- Auto-continue ------------------------------------------------------------

# Track last seen output per pane to detect "unchanged for 30s"
_pane_last_seen: dict[str, tuple[str, float]] = {}  # pane_id -> (hash, timestamp)


def maybe_continue_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    If pane shows a SAFE_AUTO_APPROVE prompt and hasn't changed for 30s, send Y.
    NEVER responds to NEVER_AUTO_APPROVE patterns.
    """
    output = capture_pane(state.pane_id, lines=20)
    h = pane_hash(output)
    now = time.time()

    prev_hash, prev_ts = _pane_last_seen.get(state.pane_id, ("", 0.0))

    if h != prev_hash:
        # Output changed -- update tracker
        _pane_last_seen[state.pane_id] = (h, now)
        return False

    # Output unchanged -- check if it's been >=30s
    if now - prev_ts < 30.0:
        return False

    # Check for dangerous patterns first (absolute veto)
    if NEVER_AUTO_APPROVE_RE.search(output):
        return False

    # Now check for safe patterns
    if not SAFE_AUTO_APPROVE_RE.search(output):
        return False

    last = pane_last_line(output)
    log(f"[{state.name}] Auto-continue: safe prompt detected ({last!r:.60})")

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would send Y + Enter")
        return False

    send_keys(state.pane_id, "Y")
    send_enter(state.pane_id)
    _pane_last_seen[state.pane_id] = (pane_hash(""), now)  # reset tracker

    db_log_heal(conn, state.name, "auto_continue", "safe_prompt",
                f"prompt={last!r:.80}")
    return True


# -- Token tracking -----------------------------------------------------------

def parse_tokens_from_pane(output: str) -> dict:
    """
    Attempt to parse token/cost information from pane output.
    Returns dict with keys: input_tokens, output_tokens, cache_tokens, cost_usd, context_pct.
    All values may be 0/None if not found.
    """
    result = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "cost_usd": 0.0,
        "context_pct": 0.0,
    }

    for line in output.splitlines():
        # "Tokens: 12,345 input / 4,567 output"
        m = TOKEN_PATTERNS[0].search(line)
        if m:
            result["input_tokens"] = int(m.group(1).replace(",", ""))
            result["output_tokens"] = int(m.group(2).replace(",", ""))
            continue

        # "Context: 45%"
        m = TOKEN_PATTERNS[1].search(line)
        if m:
            result["context_pct"] = float(m.group(1))
            continue

        # "Cost: $0.42"
        m = TOKEN_PATTERNS[2].search(line)
        if m:
            result["cost_usd"] = float(m.group(1))
            continue

    return result


def scan_tokens_for_agent(
    state: AgentState, conn: sqlite3.Connection, agent_models: dict[str, str]
) -> None:
    """Capture pane output and attempt to extract token data. Upserts to DB."""
    output = capture_pane(state.pane_id, lines=50)
    if not output.strip():
        return

    parsed = parse_tokens_from_pane(output)

    # If we found token counts but no cost, compute from rates
    if parsed["input_tokens"] or parsed["output_tokens"]:
        model_key = agent_models.get(state.name, state.model)
        # Normalize model key to opus/sonnet
        if "opus" in model_key:
            rate_key = "opus"
        else:
            rate_key = "sonnet"
        rates = COST_RATES.get(rate_key, COST_RATES["sonnet"])

        if parsed["cost_usd"] == 0.0:
            parsed["cost_usd"] = (
                parsed["input_tokens"] * rates["input"]
                + parsed["output_tokens"] * rates["output"]
                + parsed["cache_tokens"] * rates["cache_read"]
            )

        db_upsert_token_usage(
            conn,
            state.name,
            parsed["input_tokens"],
            parsed["output_tokens"],
            parsed["cache_tokens"],
            parsed["cost_usd"],
            parsed["context_pct"],
        )


# -- Spend alerts + hard cap --------------------------------------------------

_spend_alert_sent_date = ""  # track which date we sent the 80% alert


def check_spend(
    agent_states: dict[str, AgentState],
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> None:
    """Query today's total spend, send alerts or pause agents if needed."""
    global _spend_alert_sent_date

    total = db_today_total_spend(conn)
    today = now_date()

    if total >= SPEND_CAP_USD:
        log(f"SPEND CAP HIT: ${total:.2f} >= ${SPEND_CAP_USD:.2f} -- pausing non-critical agents", "WARN")
        if not dry_run:
            for name, state in agent_states.items():
                if name not in CRITICAL_AGENTS:
                    log(f"[{name}] Pausing (Ctrl+C) -- daily spend cap reached")
                    send_keys(state.pane_id, "C-c")
                    state.status = "paused"
                    db_log_heal(
                        conn, name, "paused", "spend_cap",
                        f"total_spend=${total:.2f}"
                    )
            notify_ceo(
                f"[guardian] SPEND CAP ${SPEND_CAP_USD} REACHED (${total:.2f} today). "
                f"Non-critical agents paused. Resume manually."
            )
    elif total >= SPEND_ALERT_USD and _spend_alert_sent_date != today:
        log(f"SPEND ALERT: ${total:.2f} >= ${SPEND_ALERT_USD:.2f} (80% of daily cap)", "WARN")
        if not dry_run:
            notify_ceo(
                f"[guardian] Spend alert: ${total:.2f} today "
                f"({100 * total / SPEND_CAP_USD:.0f}% of ${SPEND_CAP_USD:.2f} cap). "
                f"Watching closely."
            )
            _spend_alert_sent_date = today


# -- Bridge daemon watchdog ---------------------------------------------------

_bridge_pid: int = 0


def ensure_bridge_running(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """Start or restart the bridge daemon if it's not running."""
    global _bridge_pid

    if not BRIDGE_SCRIPT.exists():
        return

    # Check if existing PID is still alive
    if _bridge_pid > 0:
        try:
            os.kill(_bridge_pid, 0)  # 0 = probe, not kill
            return  # Still running
        except (ProcessLookupError, PermissionError):
            log(f"Bridge daemon (PID {_bridge_pid}) died -- restarting", "WARN")
            db_log_heal(conn, "system", "bridge_restart", f"pid={_bridge_pid}_died")
            _bridge_pid = 0

    # Check if bridge is running under any PID
    bridge_name = BRIDGE_SCRIPT.name
    try:
        r = subprocess.run(
            ["pgrep", "-f", bridge_name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            pids = r.stdout.strip().splitlines()
            _bridge_pid = int(pids[0])
            return  # Already running
    except (subprocess.SubprocessError, ValueError, OSError):
        pass

    # Not running -- start it
    log(f"Starting bridge daemon ({bridge_name})")
    if dry_run:
        log(f"DRY-RUN: would start {bridge_name}")
        return

    try:
        proc = subprocess.Popen(
            [sys.executable, str(BRIDGE_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _bridge_pid = proc.pid
        log(f"Bridge daemon started with PID {_bridge_pid}")
        db_log_heal(conn, "system", "bridge_start", "guardian_init",
                    f"pid={_bridge_pid}")
    except OSError as e:
        err(f"Failed to start bridge daemon: {e}")


# -- System guard cycle -------------------------------------------------------

def system_guard_cycle(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    """
    Temperature, memory, and CPU checks.
    Kills offending agents when thresholds exceeded.
    """
    temp = read_temp_celsius()
    mem_free = read_mem_free_mb()
    cpu_pct = read_cpu_pct()

    # Temperature -- kill newest agent
    if temp > TEMP_LIMIT_C:
        warn(f"THERMAL WARNING: {temp} C > {TEMP_LIMIT_C} C")
        pid, name = find_newest_claude_pid()
        if pid:
            warn(f"Killing newest agent {name!r} (PID {pid}) to reduce thermal load")
            if not dry_run:
                kill_pid(pid)
                db_log_heal(
                    conn, name, "thermal_kill", f"temp={temp}C",
                    f"pid={pid}"
                )
        else:
            warn("No claude agent processes found to kill")

    # Memory -- kill heaviest agent
    if mem_free < MEM_MIN_MB:
        warn(f"MEMORY WARNING: {mem_free}MB free < {MEM_MIN_MB}MB limit")
        pid, name = find_heaviest_claude_pid()
        if pid:
            warn(f"Killing heaviest agent {name!r} (PID {pid}) to free memory")
            if not dry_run:
                kill_pid(pid)
                db_log_heal(
                    conn, name, "memory_kill", f"free_mem={mem_free}MB",
                    f"pid={pid}"
                )
        else:
            warn("No claude agent processes found to kill")

    # CPU -- log only (spikes are transient)
    if cpu_pct > CPU_WARN_PCT:
        try:
            claude_count = int(
                subprocess.run(
                    ["pgrep", "-c", "-f", "claude"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip() or "0"
            )
        except (subprocess.SubprocessError, ValueError):
            claude_count = 0
        warn(
            f"CPU WARNING: {cpu_pct:.0f}% > {CPU_WARN_PCT}% "
            f"(agents: {claude_count}, temp: {temp} C, free: {mem_free}MB)"
        )

    # Periodic status line (every cycle)
    log(
        f"System: temp={temp} C cpu={cpu_pct:.0f}% mem_free={mem_free}MB"
    )


# -- Check mode ---------------------------------------------------------------

def run_check(agent_states: dict[str, AgentState]) -> None:
    """Dry-run: print state of all detectable agents, no actions taken."""
    print("=" * 60)
    print(f"soul-guardian v{VERSION} -- DRY RUN CHECK")
    print(f"Timestamp: {now_iso()}")
    print(f"Team: {TEAM_NAME}")
    print(f"DB: {DB_PATH}")
    print("=" * 60)

    # System health
    temp = read_temp_celsius()
    mem_free = read_mem_free_mb()
    cpu_pct = read_cpu_pct()
    print(f"\nSystem Health:")
    print(f"  Temperature : {temp} C  (limit: {TEMP_LIMIT_C} C) {'[WARN]' if temp > TEMP_LIMIT_C else '[OK]'}")
    print(f"  Free Memory : {mem_free}MB  (min: {MEM_MIN_MB}MB) {'[WARN]' if mem_free < MEM_MIN_MB else '[OK]'}")
    print(f"  CPU Usage   : {cpu_pct:.0f}%  (warn: {CPU_WARN_PCT}%) {'[WARN]' if cpu_pct > CPU_WARN_PCT else '[OK]'}")

    # Bridge status
    bridge_running = False
    bridge_name = BRIDGE_SCRIPT.name
    try:
        r = subprocess.run(
            ["pgrep", "-f", bridge_name],
            capture_output=True, text=True, timeout=5,
        )
        bridge_running = r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        pass
    print(f"\nBridge daemon ({bridge_name}): {'running' if bridge_running else 'NOT RUNNING'}")

    # Agent states
    print(f"\nAgents ({len(agent_states)}):")
    for name, state in sorted(agent_states.items()):
        output = capture_pane(state.pane_id, lines=5)
        last = pane_last_line(output)
        is_shell = pane_is_shell_prompt(last) if last else False
        has_compact = bool(COMPACT_TRIGGER_RE.search(output))
        has_safe_prompt = bool(SAFE_AUTO_APPROVE_RE.search(output)) and not bool(NEVER_AUTO_APPROVE_RE.search(output))

        print(
            f"  {name:<10} pane={state.pane_id:<4} model={state.model:<8} "
            f"machine={state.machine:<10} status={state.status}"
        )
        print(f"             last_line={last!r:.60}")
        flags = []
        if is_shell:
            flags.append("SHELL_PROMPT_DETECTED")
        if has_compact:
            flags.append("COMPACT_TRIGGER")
        if has_safe_prompt:
            flags.append("SAFE_PROMPT")
        if flags:
            print(f"             flags=[{', '.join(flags)}]")

    # DB summary
    try:
        conn = db_connect()
        db_init(conn)
        today_spend = db_today_total_spend(conn)
        heal_count = conn.execute(
            "SELECT COUNT(*) FROM self_heal_events"
        ).fetchone()[0]
        print(f"\nDatabase ({DB_PATH}):")
        print(f"  Today's spend : ${today_spend:.4f}")
        print(f"  Heal events   : {heal_count} total")
        conn.close()
    except sqlite3.Error as e:
        print(f"\nDatabase error: {e}")

    print("\n[CHECK COMPLETE -- no actions taken]")


# -- Main loop ----------------------------------------------------------------

_running = True


def handle_sigterm(signum, frame):
    global _running
    log("Received SIGTERM -- shutting down gracefully")
    _running = False


def build_agent_states(agent_models: dict[str, str]) -> dict[str, AgentState]:
    """Build initial AgentState dict from pane map + TOML config."""
    pane_map = build_agent_pane_map()
    states: dict[str, AgentState] = {}

    # Load machine assignments from TOML
    machine_map: dict[str, str] = {}
    try:
        content = SOUL_TEAM_TOML.read_text()
        current_name = None
        current_machine = None
        for line in content.splitlines():
            line = line.strip()
            if line == "[[agents]]":
                if current_name and current_machine:
                    machine_map[current_name] = current_machine
                current_name = None
                current_machine = None
            elif line.startswith("name ="):
                current_name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("machine ="):
                current_machine = line.split("=", 1)[1].strip().strip('"')
        if current_name and current_machine:
            machine_map[current_name] = current_machine
    except OSError:
        pass

    for name, pane_id in pane_map.items():
        model = agent_models.get(name, "sonnet")
        machine = machine_map.get(name, "local")
        states[name] = AgentState(name, pane_id, model, machine)

    if not states:
        log("No agent panes found -- is the team session running?", "WARN")

    return states


def run_daemon(dry_run: bool = False, once: bool = False) -> None:
    """Main guardian loop."""
    signal.signal(signal.SIGTERM, handle_sigterm)

    log(f"soul-guardian v{VERSION} starting (dry_run={dry_run}, once={once})")
    log(f"DB: {DB_PATH} | Team: {TEAM_NAME}")

    conn = db_connect()
    db_init(conn)
    log("SQLite schema initialized")

    # Load machines config for remote agent launch
    load_machines_config()
    if _machines_config:
        log(f"Machines config loaded: {list(_machines_config.keys())}")

    agent_models = load_agent_models()
    log(f"Agent models: {agent_models}")

    agent_states = build_agent_states(agent_models)
    log(f"Detected agents: {list(agent_states.keys())}")

    last_token_scan = 0.0
    last_spend_check = 0.0

    iteration = 0
    while _running:
        iteration += 1
        now = time.time()

        try:
            # -- System guard (temp / mem / cpu) -- every 30s
            system_guard_cycle(conn, dry_run=dry_run)

            # -- Bridge watchdog -- every cycle
            ensure_bridge_running(conn, dry_run=dry_run)

            # -- Refresh agent pane map (agents may have been relaunched)
            if iteration % 5 == 0:  # every 150s
                updated_map = build_agent_pane_map()
                for name, pane_id in updated_map.items():
                    if name not in agent_states:
                        model = agent_models.get(name, "sonnet")
                        agent_states[name] = AgentState(name, pane_id, model, "local")
                        log(f"[{name}] New agent pane detected: {pane_id}")

            # -- Per-agent checks
            for name, state in list(agent_states.items()):
                if not state.pane_id:
                    continue

                # Auto-restart
                maybe_restart_agent(state, conn, dry_run=dry_run)

                # Auto-compact
                maybe_compact_agent(state, conn, dry_run=dry_run)

                # Auto-continue
                maybe_continue_agent(state, conn, dry_run=dry_run)

            # -- Token tracking -- every 60s
            if now - last_token_scan >= TOKEN_INTERVAL_S:
                for name, state in agent_states.items():
                    try:
                        scan_tokens_for_agent(state, conn, agent_models)
                    except Exception as e:
                        warn(f"[{name}] Token scan error: {e}")
                last_token_scan = now

            # -- Spend check -- every 60s
            if now - last_spend_check >= SPEND_INTERVAL_S:
                check_spend(agent_states, conn, dry_run=dry_run)
                last_spend_check = now

        except Exception as e:
            err(f"Guardian loop error (iteration {iteration}): {e}")

        if once:
            break

        # Sleep in small increments so SIGTERM is responsive
        for _ in range(MAIN_INTERVAL_S * 2):  # 30s in 0.5s steps
            if not _running:
                break
            time.sleep(0.5)

    log("soul-guardian shutdown complete")
    conn.close()


# -- Entry point --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=f"soul-guardian v{VERSION} -- System watchdog for agent teams"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: print state of all detectable agents, no actions taken",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one cycle then exit (useful for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect conditions but take no actions (log only)",
    )
    args = parser.parse_args()

    if args.check:
        agent_models = load_agent_models()
        agent_states = build_agent_states(agent_models)
        run_check(agent_states)
    else:
        run_daemon(dry_run=args.dry_run, once=args.once)


if __name__ == "__main__":
    main()
