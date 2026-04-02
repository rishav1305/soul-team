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
    SOUL_TEAM_TOML         Path to team TOML (default: ~/.claude/config/soul-team.toml)
    SOUL_BRIDGE_SCRIPT     Path to bridge daemon script (optional)
    SOUL_MSG_BIN           Path to messaging binary (optional)
    SOUL_CRITICAL_AGENTS   Comma-separated agent names that must never be paused (default: empty)
    SOUL_MACHINES_JSON     Path to JSON file mapping machine names to SSH targets (optional)
"""

import argparse
import fcntl
import hashlib
import json
import shlex
import threading
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

# -- Constants ----------------------------------------------------------------

VERSION = "2.5.0"

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
RESTART_STAGGER_S = 90         # min seconds between consecutive agent restarts (boot storm)
IDLE_WAKE_STAGGER_S = 20       # min seconds between idle-wake restarts (surgical)

# Idle shutdown
IDLE_TIMEOUT_S = 900           # 15 min of no pane activity before shutdown
IDLE_PRE_EXIT_WAIT_S = 30     # save window before /exit
IDLE_CHECK_INTERVAL_S = 60    # check idle state every minute
IDLE_WAKE_BOOT_WAIT_S = 3     # wait for TUI after launch (no trust prompt)
IDLE_WAKE_DEDUP_S = 5          # dedup window for inbox watcher events
IDLE_POLL_FALLBACK_S = 300    # 5 min periodic poll as inotify safety net

# Hot period (disable idle shutdown during launch days)
HOT_PERIOD_FILE = Path.home() / ".soul" / "hot-period"

# Auto-compact
COMPACT_COOLDOWN_S = 300   # 5 minutes
COMPACT_PRE_SAVE_WAIT_S = 30  # seconds to wait after injecting save directive
MSG_COUNT_COMPACT_THRESHOLD = 100

# Context budget monitor
CONTEXT_EARLY_COMPACT_PCT = 70.0  # Trigger compact at 70% context usage
CONTEXT_LOG_PCT = 50.0            # Start logging at 50% context usage

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

# Auto-continue: ONLY match Claude Code's own tool permission prompts.
# These are tightly scoped to prevent matching arbitrary [Y/n] from shell commands.
SAFE_AUTO_APPROVE_RE = re.compile(
    r"("
    r"Allow\s+(?:Read|Write|Edit|Bash|Glob|Grep|WebSearch|WebFetch|Skill|Agent|mcp__)"  # Claude Code tool permission
    r"|Do you want to proceed\?.*\[Y/n\]"  # Claude Code proceed prompt
    r"|Press Enter to continue"            # Claude Code output continuation
    r"|Allow [\w-]+ tool"                  # Generic tool permission "Allow X tool?"
    r")",
    re.IGNORECASE,
)

# NEVER auto-answer -- dangerous confirmations (expanded blocklist)
NEVER_AUTO_APPROVE_RE = re.compile(
    r"("
    r"Which model"
    r"|Enter.*password"
    r"|Delete.*\?"
    r"|Force push"
    r"|Drop.*table"
    r"|rm\s+"
    r"|chmod\b"
    r"|chown\b"
    r"|git\s+reset"
    r"|git\s+push.*force"
    r"|curl\s.*\|"
    r"|pip\s+install"
    r"|npm\s+install"
    r"|ssh-keygen"
    r"|sudo\b"
    r"|mkfs\b"
    r"|dd\s+if="
    r"|>/dev/"
    r"|truncate\b"
    r"|shred\b"
    r")",
    re.IGNORECASE,
)

# Token patterns Claude Code may print (heuristic -- parse what's available)
TOKEN_PATTERNS = [
    # "Tokens: 12,345 input / 4,567 output"
    re.compile(
        r"[Tt]okens?:\s*([\d,]+)\s+input\s*/\s*([\d,]+)\s+output",
        re.IGNORECASE,
    ),
    # "Context: 45%" or "ctx:45%" (Claude Code status bar format)
    re.compile(r"(?:[Cc]ontext(?:\s+window)?:\s*|ctx:)(\d+(?:\.\d+)?)\s*%"),
    # "Cost: $0.42" or similar
    re.compile(r"[Cc]ost:\s*\$?([\d.]+)"),
]

# JSONL-based token tracking state
_jsonl_offsets: dict[str, int] = {}   # file_path -> last byte offset
_agent_jsonl_map: dict[str, str] = {}  # agent_name -> active JSONL path
_jsonl_map_refresh_ts: float = 0.0     # last time we refreshed the map
JSONL_MAP_REFRESH_S = 300              # refresh agent→JSONL mapping every 5 min

# Queue depth alerting
QUEUE_DEPTH_LIMIT = 20                 # alert when any agent queue exceeds this
QUEUE_CHECK_INTERVAL_S = 120           # check queue depth every 2 minutes

# -- Configurable Paths -------------------------------------------------------

HOME = Path.home()
CLAUDE_PROJECTS_DIR = HOME / ".claude" / "projects"

# Memory enforcement
MEMORY_SCANNER_PATH = HOME / ".claude" / "scripts" / "memory-scanner.py"
POST_RESTART_AUDIT_DELAY_S = 45  # wait for agent to boot before auditing

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
    os.environ.get("SOUL_TEAM_TOML", str(HOME / ".claude" / "config" / "soul-team.toml"))
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
QUEUE_DIR = HOME / ".clawteam" / "teams" / "soul-team" / "queue"

# Valid agent names — only these are allowed in DB writes
VALID_AGENTS = frozenset({
    "pepper", "xavier", "hawkeye", "fury", "loki",
    "happy", "shuri", "stark", "banner", "friday", "team-lead", "system",
    "unknown",  # sentinel for when agent name can't be determined from process args
})

def _is_valid_agent(name: str) -> bool:
    """Check if agent name is in the known valid agent set.

    Strict validation: only names in VALID_AGENTS are accepted.
    Update VALID_AGENTS when adding new agents to the team.
    """
    return bool(name) and name in VALID_AGENTS


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
    # Use local time (IST) for daily boundaries — matches when the user's "day" resets
    return datetime.now().date().isoformat()


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

_db_lock = threading.Lock()


def _retry_on_busy(func):
    """Decorator: acquires _db_lock and retries on SQLITE_BUSY (3 attempts, 100ms backoff)."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_err = None
        for attempt in range(3):
            try:
                with _db_lock:
                    return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    last_err = e
                    time.sleep(0.1 * (attempt + 1))
                else:
                    raise
        raise last_err  # type: ignore[misc]
    return wrapper


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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

        CREATE TABLE IF NOT EXISTS memory_audit (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent TEXT NOT NULL,
            trigger TEXT NOT NULL,
            total_directives INTEGER DEFAULT 0,
            saved INTEGER DEFAULT 0,
            unsaved INTEGER DEFAULT 0,
            passed INTEGER DEFAULT 0,
            details TEXT
        );
    """)
    conn.commit()


@_retry_on_busy
def db_log_heal(conn: sqlite3.Connection, agent: str, event_type: str,
                trigger: str, details: str = "") -> None:
    conn.execute(
        "INSERT INTO self_heal_events (timestamp, agent, event_type, trigger, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (now_iso(), agent, event_type, trigger, details),
    )
    conn.commit()


@_retry_on_busy
def db_log_memory_audit(conn: sqlite3.Connection, agent: str,
                        trigger: str, total: int, saved: int,
                        unsaved: int, passed: bool, details: str = "") -> None:
    conn.execute(
        "INSERT INTO memory_audit "
        "(timestamp, agent, trigger, total_directives, saved, unsaved, passed, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now_iso(), agent, trigger, total, saved, unsaved, int(passed), details),
    )
    conn.commit()


@_retry_on_busy
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

def _load_toml_agents() -> list[dict]:
    """Load [[agents]] list from soul-team.toml using stdlib tomllib."""
    try:
        with open(SOUL_TEAM_TOML, "rb") as f:
            data = tomllib.load(f)
        return data.get("agents", [])
    except (OSError, tomllib.TOMLDecodeError):
        return []


def load_agent_models() -> dict[str, str]:
    """Load agent -> model mapping from soul-team.toml."""
    return {
        a["name"]: a.get("model", "sonnet")
        for a in _load_toml_agents()
        if "name" in a
    }


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
                if name and name != "team-lead":
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
        self.compacted_this_session = False  # True after first compact — prevents re-firing
        self.msg_count = 0
        self.status = "active"  # active | idle | stuck | crashed | unreachable | idle_shutdown
        self.restart_timestamps: list[float] = []  # last N restart times
        self.spend_alert_sent_today = False
        self.spend_date = ""
        self.last_activity_ts = time.time()  # last pane output change

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


class _PaneLock:
    """Cross-process file lock for tmux pane writes.

    Uses fcntl.flock on /tmp/soul-pane-{pane_id}.lock to prevent
    interleaved writes from guardian and courier to the same pane.
    """

    def __init__(self, pane_id: str):
        # Sanitize pane_id for filename (e.g. %5 -> _5)
        safe_id = pane_id.replace("%", "_").replace("/", "_")
        self._path = f"/tmp/soul-pane-{safe_id}.lock"
        self._fd = None

    def __enter__(self):
        self._fd = open(self._path, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
        return False


def send_keys(pane_id: str, text: str) -> bool:
    """Send literal text to a tmux pane via send-keys -l.

    Uses the -l flag to prevent tmux from interpreting special key sequences
    (e.g., C-c, Enter). For actual key sequences, use send_raw_keys().
    Acquires cross-process pane lock to prevent interleaved writes.
    """
    try:
        with _PaneLock(pane_id):
            r = subprocess.run(
                ["tmux", "send-keys", "-l", "-t", pane_id, text],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def send_raw_keys(pane_id: str, keys: str) -> bool:
    """Send raw key sequences to a tmux pane (NO -l flag).

    Use this for actual key sequences like 'Enter', 'C-c', 'Escape'.
    For literal text injection, use send_keys() instead.
    Acquires cross-process pane lock to prevent interleaved writes.
    """
    try:
        with _PaneLock(pane_id):
            r = subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, keys],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def send_enter(pane_id: str) -> bool:
    """Send Enter key to a tmux pane."""
    return send_raw_keys(pane_id, "Enter")


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
                name = m.group(1).lower() if m else "unknown"
                if not _is_valid_agent(name):
                    name = "unknown"
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
            name = m.group(1).lower() if m else "unknown"
            if not _is_valid_agent(name):
                name = "unknown"
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


def check_queue_depth(dry_run: bool = False) -> None:
    """Check courier queue depth for each agent. Alert when > QUEUE_DEPTH_LIMIT."""
    if not QUEUE_DIR.is_dir():
        return
    for queue_file in QUEUE_DIR.glob("*.json"):
        agent_name = queue_file.stem
        try:
            data = json.loads(queue_file.read_text())
            if not isinstance(data, list):
                continue
            depth = len(data)
            if depth > QUEUE_DEPTH_LIMIT:
                msg = f"[queue-depth] {agent_name}: {depth} messages (limit {QUEUE_DEPTH_LIMIT})"
                warn(msg)
                if not dry_run:
                    notify_ceo(msg)
        except (OSError, json.JSONDecodeError):
            continue


# -- Agent Launch Command -----------------------------------------------------

def build_launch_cmd(agent_name: str, model: str, machine: str) -> list[str] | None:
    """
    Build the tmux send-keys command to re-launch a claude agent in its pane.
    Mirrors what the launcher script does.

    For remote machines, reads SSH target from the machines config file
    (SOUL_MACHINES_JSON). For local agents, optionally wraps with systemd-run
    into a cgroup slice.
    """
    # Validate agent name to prevent shell injection via crafted names
    if not re.match(r'^[a-z][a-z0-9-]*$', agent_name):
        err(f"Invalid agent name: {agent_name!r}")
        return None

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

    # Dev agents (shuri, happy) load additional code conventions
    DEV_AGENTS = {"shuri", "happy"}
    dev_flag = ""
    if agent_name in DEV_AGENTS:
        dev_md = HOME / ".claude" / "CLAUDE-dev.md"
        if dev_md.exists():
            dev_flag = f" --append-system-prompt-file {dev_md}"

    base_cmd = (
        f"cd {HOME} && "
        f"env CLAUDECODE=1 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 "
        f"{claude_bin} "
        f"--agent-id {agent_name}@{TEAM_NAME} "
        f"--agent-name {agent_name} "
        f"--team-name {TEAM_NAME} "
        f"--agent-type {agent_name} "
        f"--permission-mode bypassPermissions "
        f"--model {model_str}"
        f"{dev_flag}"
    )

    # Check if this machine is a remote target from config
    machine_cfg = _machines_config.get(machine, {})
    ssh_target = machine_cfg.get("ssh_target", "")

    if ssh_target:
        # Re-launch via SSH to remote machine
        ssh_args = machine_cfg.get("ssh_args", [])
        return ["ssh"] + ssh_args + [ssh_target, base_cmd]

    # Local -- wrap with systemd-run into cgroup slice (if available)
    # NOTE: base_cmd starts with "cd ..." which is a shell builtin, not an
    # executable.  systemd-run -- cd ... fails with "Failed to find executable
    # cd".  Wrapping in bash -c solves this.
    cgroup_cmd = (
        f"systemd-run --user --scope --slice=soul-agents.slice "
        f"-- bash -c {shlex.quote(base_cmd)}"
    )
    return ["bash", "-c", cgroup_cmd]


# -- Auto-restart -------------------------------------------------------------

def restart_count_last_hour(state: AgentState) -> int:
    cutoff = time.time() - 3600
    state.restart_timestamps = [t for t in state.restart_timestamps if t > cutoff]
    return len(state.restart_timestamps)


# Global restart stagger: track last restart time across ALL agents
_last_restart_ts: float = 0.0


def maybe_restart_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Check if this agent's pane is showing a shell prompt (crashed out of Claude).
    If so, re-launch up to MAX_RESTARTS_PER_HOUR per hour.
    Returns True if restart was triggered.
    """
    # Don't restart agents that were intentionally paused (e.g., spend cap)
    if state.status == "paused":
        return False

    output = capture_pane(state.pane_id, lines=10)
    last = pane_last_line(output)

    if not pane_is_shell_prompt(last):
        return False

    # Stagger: don't restart if another agent was restarted recently
    global _last_restart_ts
    since_last = time.time() - _last_restart_ts
    if since_last < RESTART_STAGGER_S:
        remaining = int(RESTART_STAGGER_S - since_last)
        log(
            f"[{state.name}] Shell prompt detected but stagger active "
            f"({remaining}s remaining) -- deferring restart"
        )
        return False

    # Check per-agent cooldown
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
        now_ts = time.time()
        state.restart_timestamps.append(now_ts)
        _last_restart_ts = now_ts  # Update global stagger timestamp
        state.status = "active"
        state.compacted_this_session = False  # Reset compact flag on restart
        db_log_heal(
            conn, state.name, "restart", "shell_prompt",
            f"last_line={last!r:.80} restart_count={count + 1}"
        )
        log(f"[{state.name}] Restarted (cmd sent to pane {state.pane_id})")
        # Schedule memory re-read injection after agent boots
        _pending_memory_audits[state.name] = now_ts + POST_RESTART_AUDIT_DELAY_S
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


# -- Memory enforcement -------------------------------------------------------

_pending_memory_audits: dict[str, float] = {}  # agent -> scheduled_time


def inject_memory_reread(state: AgentState, conn: sqlite3.Connection,
                         dry_run: bool = False) -> bool:
    """
    After restart, inject a P1 message telling the agent to re-read its memory
    and shared KB before doing anything else.
    """
    msg = (
        "[P1 INTERRUPT from guardian] You were just restarted. "
        "Before doing anything, READ your memory files at "
        "~/.claude/agent-memory/{name}/ and the shared knowledge base at "
        "~/soul-roles/shared/knowledge-base/. "
        "Do not accept any tasks until you have re-read your context. "
        "Then: check your interrupted-state memory and resume if applicable, "
        "and check your inbox via clawteam."
    ).format(name=state.name)

    log(f"[{state.name}] Injecting post-restart memory re-read P1")

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would inject memory re-read P1")
        return False

    success = send_keys(state.pane_id, msg)
    if success:
        send_enter(state.pane_id)
        db_log_heal(conn, state.name, "memory_reread_inject", "post_restart")
        # Schedule a memory audit for this agent
        _pending_memory_audits[state.name] = time.time() + POST_RESTART_AUDIT_DELAY_S
        return True
    return False


def run_memory_audit(agent: str, conn: sqlite3.Connection,
                     trigger: str = "manual") -> dict:
    """
    Run the memory scanner for a specific agent and log results.
    Returns dict with audit results.
    """
    if not MEMORY_SCANNER_PATH.exists():
        warn(f"Memory scanner not found at {MEMORY_SCANNER_PATH}")
        return {"error": "scanner_not_found"}

    try:
        result = subprocess.run(
            ["python3", str(MEMORY_SCANNER_PATH), "--check", "--agent", agent, "--json"],
            capture_output=True, text=True, timeout=60,
        )
        output = result.stdout.strip()
        if not output:
            warn(f"[{agent}] Memory scanner returned empty output")
            return {"error": "empty_output"}

        data = json.loads(output)
        if not data:
            return {"error": "no_data"}

        report = data[0]  # Single agent
        total = report.get("total_directives", 0)
        saved = report.get("saved", 0)
        unsaved = report.get("unsaved", 0)
        passed = report.get("pass", True)

        db_log_memory_audit(
            conn, agent, trigger, total, saved, unsaved, passed,
            f"memory_files={len(report.get('memory_files', []))}"
        )

        if not passed:
            warn(
                f"[{agent}] MEMORY AUDIT FAILED: {unsaved} unsaved directives "
                f"out of {total} total"
            )
            notify_ceo(
                f"[guardian] Memory audit FAILED for {agent}: "
                f"{unsaved}/{total} directives not saved to memory"
            )
        else:
            log(f"[{agent}] Memory audit PASSED: {saved}/{total} directives saved")

        return report

    except subprocess.TimeoutExpired:
        err(f"[{agent}] Memory scanner timed out")
        return {"error": "timeout"}
    except (json.JSONDecodeError, OSError) as e:
        err(f"[{agent}] Memory scanner error: {e}")
        return {"error": str(e)}


def check_pending_memory_audits(agent_states: dict, conn: sqlite3.Connection,
                                dry_run: bool = False) -> None:
    """Check and run any pending memory audits (scheduled after restarts/compacts)."""
    now = time.time()
    completed = []
    for agent, scheduled_time in _pending_memory_audits.items():
        if now >= scheduled_time:
            if dry_run:
                log(f"[{agent}] DRY-RUN: would run post-restart memory audit")
            else:
                # Inject memory re-read P1 if agent has a pane
                state = agent_states.get(agent)
                if state and state.pane_id:
                    inject_memory_reread(state, conn, dry_run=dry_run)
                # Run the scanner
                run_memory_audit(agent, conn, trigger="post_restart")
            completed.append(agent)
    for agent in completed:
        del _pending_memory_audits[agent]


# -- Auto-compact -------------------------------------------------------------

def maybe_compact_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Send /compact if context warning detected or msg_count threshold exceeded.
    Only fires once per session.
    """
    if state.compacted_this_session:
        return False

    now = time.time()

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

    # Pre-compact: inject directive save message, wait, then compact
    save_msg = (
        "CONTEXT COMPACT INCOMING — You have 30 seconds. "
        "Save any unsaved CEO directives, decisions, or important state "
        "to your memory or shared KB NOW. Then compaction will proceed."
    )
    log(f"[{state.name}] Injecting pre-compact save directive")
    send_keys(state.pane_id, save_msg)
    send_enter(state.pane_id)
    db_log_heal(conn, state.name, "pre_compact_save_inject", trigger)

    # Wait for agent to process the save request
    time.sleep(COMPACT_PRE_SAVE_WAIT_S)

    # Now send compact
    send_keys(state.pane_id, "/compact")
    send_enter(state.pane_id)
    state.last_compact_ts = time.time()
    state.compacted_this_session = True
    db_log_heal(conn, state.name, "compact", trigger)

    # Schedule memory audit after compact settles
    _pending_memory_audits[state.name] = time.time() + POST_RESTART_AUDIT_DELAY_S

    return True


# -- Context budget monitor ----------------------------------------------------

_context_alerts_sent: dict[str, float] = {}  # agent -> last alert timestamp


def check_context_budget(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Parse context percentage from pane output.
    If >= CONTEXT_EARLY_COMPACT_PCT (70%), trigger early compact.
    Returns True if compact was triggered.
    """
    # Only compact once per session — prevents repeated 70% triggers
    if state.compacted_this_session:
        return False

    now = time.time()

    output = capture_pane(state.pane_id, lines=50)
    if not output.strip():
        return False

    # Parse context percentage from pane
    ctx_pct = 0.0
    for line in output.splitlines():
        m = TOKEN_PATTERNS[1].search(line)  # "Context: 45%" pattern
        if m:
            ctx_pct = float(m.group(1))
            break

    if ctx_pct < CONTEXT_LOG_PCT:
        return False

    # Log at 50%+ for monitoring
    log(f"[{state.name}] Context usage: {ctx_pct:.0f}%")

    # Trigger early compact at 70%+
    if ctx_pct >= CONTEXT_EARLY_COMPACT_PCT:
        trigger = f"context_budget={ctx_pct:.0f}%"
        log(
            f"[{state.name}] CONTEXT BUDGET WARNING: {ctx_pct:.0f}% >= "
            f"{CONTEXT_EARLY_COMPACT_PCT:.0f}% threshold -- triggering early compact"
        )

        if dry_run:
            log(f"[{state.name}] DRY-RUN: would trigger early compact")
            return False

        # Pre-compact save directive
        save_msg = (
            "CONTEXT COMPACT INCOMING — You have 30 seconds. "
            "Save any unsaved CEO directives, decisions, or important state "
            "to your memory or shared KB NOW. Then compaction will proceed."
        )
        log(f"[{state.name}] Injecting pre-compact save directive (context budget)")
        send_keys(state.pane_id, save_msg)
        send_enter(state.pane_id)
        db_log_heal(conn, state.name, "pre_compact_save_inject", trigger)

        # Wait for agent to process the save request
        time.sleep(COMPACT_PRE_SAVE_WAIT_S)

        # Now send compact
        send_keys(state.pane_id, "/compact")
        send_enter(state.pane_id)
        state.last_compact_ts = time.time()
        state.compacted_this_session = True
        db_log_heal(conn, state.name, "compact", trigger)

        # Schedule memory audit after compact settles
        _pending_memory_audits[state.name] = time.time() + POST_RESTART_AUDIT_DELAY_S

        # Notify CEO on first 70%+ event per hour per agent
        last_alert = _context_alerts_sent.get(state.name, 0.0)
        if now - last_alert > 3600:
            notify_ceo(
                f"[guardian] {state.name} hit {ctx_pct:.0f}% context usage — "
                f"auto-compacting to prevent crash loop"
            )
            _context_alerts_sent[state.name] = now

        return True

    return False


# -- Idle shutdown ------------------------------------------------------------

# Active indicators: do NOT idle-shutdown if these appear in recent output
ACTIVE_INDICATORS = [
    "\u2801", "\u2802", "\u2804", "\u2808", "\u2810", "\u2820",  # braille spinner
    "Running", "Executing", "in_progress", "Thinking",
    "searching", "reading", "writing", "editing",
]

# Per-agent wake dedup tracking
_last_wake_ts: dict[str, float] = {}  # agent -> last wake timestamp

# Inbox paths for inotify / poll
_INBOX_DIR = HOME / "soul-roles" / "shared" / "inbox"
_COURIER_QUEUE_DIR = HOME / ".clawteam" / "teams" / TEAM_NAME / "queue"


def is_hot_period() -> bool:
    """Check if hot period mode is active (disable idle shutdown)."""
    if not HOT_PERIOD_FILE.exists():
        return False
    try:
        content = HOT_PERIOD_FILE.read_text().strip()
        expiry = datetime.fromisoformat(content)
        if datetime.now(expiry.tzinfo or None) > expiry:
            HOT_PERIOD_FILE.unlink(missing_ok=True)
            log("Hot period expired — idle shutdown re-enabled")
            return False
        return True
    except (ValueError, OSError):
        return True  # file exists but unparseable → assume hot


def has_pending_messages(agent: str) -> bool:
    """Check if agent has unprocessed inbox files or queued courier messages.

    Checks three locations:
    1. Spec inbox: ~/soul-roles/shared/inbox/{agent}/
    2. Courier queue: ~/.clawteam/teams/{team}/queue/{agent}.json
    3. Clawteam inbox: ~/.clawteam/teams/{team}/inboxes/{agent}_{agent}/
    """
    # Spec/role inbox (soul-roles/shared/inbox)
    inbox = _INBOX_DIR / agent
    if inbox.is_dir():
        for f in inbox.iterdir():
            if f.suffix in (".md", ".json", ".txt") and f.stat().st_size > 0:
                return True

    # Courier queue (clawteam queue dir)
    queue_file = _COURIER_QUEUE_DIR / f"{agent}.json"
    if queue_file.exists():
        try:
            data = json.loads(queue_file.read_text())
            if isinstance(data, list) and len(data) > 0:
                return True
        except (json.JSONDecodeError, OSError):
            pass

    # Clawteam inbox (per-agent inbox directory)
    clawteam_inbox = HOME / ".clawteam" / "teams" / TEAM_NAME / "inboxes" / f"{agent}_{agent}"
    if clawteam_inbox.is_dir():
        for f in clawteam_inbox.iterdir():
            if f.suffix in (".md", ".json", ".txt") and f.stat().st_size > 0:
                # Skip archive subdirectory entries
                if f.is_file():
                    return True

    return False


def is_agent_idle(state: AgentState) -> bool:
    """
    Check if agent has been idle for IDLE_TIMEOUT_S.
    Idle = no pane output change + no active indicators + no pending messages.
    """
    if state.status == "idle_shutdown":
        return False  # Already shut down

    output = capture_pane(state.pane_id, lines=5)
    output_hash = hashlib.md5(output.encode()).hexdigest()

    if output_hash != state.last_output_hash:
        state.last_output_hash = output_hash
        state.last_activity_ts = time.time()
        return False

    # Check for active indicators
    if any(ind in output for ind in ACTIVE_INDICATORS):
        state.last_activity_ts = time.time()
        return False

    # Check courier queue for pending messages
    if has_pending_messages(state.name):
        return False

    return (time.time() - state.last_activity_ts) >= IDLE_TIMEOUT_S


def idle_shutdown_agent(
    state: AgentState, conn: sqlite3.Connection, dry_run: bool = False
) -> bool:
    """
    Gracefully shut down an idle agent.
    Injects save directive, waits, then sends /exit.
    Returns True if shutdown was triggered.
    """
    if is_hot_period():
        log(f"[{state.name}] Hot period active — idle shutdown suppressed")
        return False

    if state.name in CRITICAL_AGENTS:
        return False

    log(f"[{state.name}] Idle for {IDLE_TIMEOUT_S}s — initiating idle shutdown")

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would idle-shutdown now")
        return False

    # Step 1: Inject pre-exit save message
    save_msg = (
        "IDLE SHUTDOWN INCOMING — You have 30 seconds. "
        "Save any unsaved state to memory NOW (interrupted-state, "
        "unsaved directives, work in progress). Then you will be exited."
    )
    send_keys(state.pane_id, save_msg)
    send_enter(state.pane_id)
    db_log_heal(conn, state.name, "idle_pre_exit_save", "idle_timeout")

    # Step 2: Wait for save
    time.sleep(IDLE_PRE_EXIT_WAIT_S)

    # Step 3: Send /exit
    send_keys(state.pane_id, "/exit")
    send_enter(state.pane_id)
    time.sleep(5)

    # Step 4: Verify exit — if TUI still showing, force it
    output = capture_pane(state.pane_id, lines=3)
    if not pane_is_shell_prompt(pane_last_line(output)):
        send_raw_keys(state.pane_id, "C-c")
        time.sleep(1)
        send_keys(state.pane_id, "/exit")
        send_enter(state.pane_id)
        time.sleep(3)

    # Step 5: Mark as idle_shutdown
    state.status = "idle_shutdown"
    db_log_heal(conn, state.name, "idle_shutdown", "idle_timeout",
                f"idle_for={IDLE_TIMEOUT_S}s")
    log(f"[{state.name}] Idle shutdown complete")

    return True


def wake_agent(
    state: AgentState, conn: sqlite3.Connection, trigger: str = "inbox_file",
    dry_run: bool = False
) -> bool:
    """
    Wake an idle-shutdown agent. Optimized path: 12-18s to first message.
    Uses IDLE_WAKE_STAGGER_S (not RESTART_STAGGER_S) for faster response.
    """
    if state.status != "idle_shutdown":
        return False

    # Dedup: skip if this agent was woken recently
    now = time.time()
    last_wake = _last_wake_ts.get(state.name, 0.0)
    if now - last_wake < IDLE_WAKE_DEDUP_S:
        return False

    # Stagger: use shorter idle-wake stagger
    global _last_restart_ts
    if now - _last_restart_ts < IDLE_WAKE_STAGGER_S:
        remaining = int(IDLE_WAKE_STAGGER_S - (now - _last_restart_ts))
        log(f"[{state.name}] Idle-wake stagger active ({remaining}s remaining)")
        return False

    log(f"[{state.name}] Waking from idle shutdown (trigger: {trigger})")

    if dry_run:
        log(f"[{state.name}] DRY-RUN: would wake now")
        return False

    # Build and send launch command
    launch_cmd = build_launch_cmd(state.name, state.model, state.machine)
    if not launch_cmd:
        err(f"[{state.name}] Could not build launch command for idle-wake")
        return False

    cmd_str = subprocess.list2cmdline(launch_cmd)
    success = send_keys(state.pane_id, cmd_str)
    if success:
        send_enter(state.pane_id)

    if not success:
        err(f"[{state.name}] send-keys failed for idle-wake")
        return False

    # Wait for TUI to load (NO trust prompt sleep — bypassPermissions mode)
    time.sleep(IDLE_WAKE_BOOT_WAIT_S)

    # Optimized boot prompt: memory + inbox only, skip daily routine
    boot_msg = (
        f"You were idle-shutdown by Guardian. "
        f"Read your memory at ~/.claude/agent-memory/{state.name}/ "
        f"then check inbox: clawteam inbox receive soul-team --agent {state.name}. "
        f"Skip daily routine — process inbox immediately."
    )
    send_keys(state.pane_id, boot_msg)
    send_enter(state.pane_id)

    # Update state
    now_ts = time.time()
    _last_restart_ts = now_ts
    _last_wake_ts[state.name] = now_ts
    state.status = "active"
    state.last_activity_ts = now_ts
    state.restart_timestamps.append(now_ts)

    db_log_heal(conn, state.name, "idle_wake", trigger)
    log(f"[{state.name}] Idle-wake complete (trigger: {trigger})")

    # Schedule memory audit after boot
    _pending_memory_audits[state.name] = now_ts + POST_RESTART_AUDIT_DELAY_S

    return True


# -- Inbox watcher (inotify thread) -------------------------------------------

class InboxWatcherThread(threading.Thread):
    """
    Background thread that watches agent inbox directories via polling.
    When a new file appears for an idle-shutdown agent, queues a wake event.
    Uses polling instead of inotify for sshfs compatibility (Pepper review note #2).
    """

    def __init__(self, agent_states: dict[str, AgentState],
                 conn: sqlite3.Connection, dry_run: bool = False):
        super().__init__(daemon=True, name="inbox-watcher")
        self.agent_states = agent_states
        self.conn = conn
        self.dry_run = dry_run
        self._stop_event = threading.Event()
        self._wake_queue: list[tuple[str, str]] = []  # (agent, trigger)
        self._lock = threading.Lock()

    def stop(self):
        self._stop_event.set()

    def get_pending_wakes(self) -> list[tuple[str, str]]:
        """Drain the wake queue. Called from main loop."""
        with self._lock:
            wakes = list(self._wake_queue)
            self._wake_queue.clear()
            return wakes

    def run(self):
        """Poll inbox dirs every IDLE_POLL_FALLBACK_S for idle agents."""
        log("[inbox-watcher] Started (poll mode for sshfs compatibility)")
        while not self._stop_event.is_set():
            try:
                for name, state in list(self.agent_states.items()):
                    if state.status != "idle_shutdown":
                        continue

                    if has_pending_messages(name):
                        with self._lock:
                            # Dedup: don't queue if already in queue
                            queued = {w[0] for w in self._wake_queue}
                            if name not in queued:
                                self._wake_queue.append((name, "inbox_poll"))
                                log(f"[inbox-watcher] {name}: pending messages detected, queuing wake")

            except Exception as e:
                warn(f"[inbox-watcher] Error during poll: {e}")

            self._stop_event.wait(IDLE_POLL_FALLBACK_S)

        log("[inbox-watcher] Stopped")


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


def _refresh_agent_jsonl_map() -> None:
    """Scan ~/.claude/projects/ to find the active JSONL file per agent.

    Scans local project dirs. For remote machines (titan-pc), uses SSH to
    find the active JSONL and copies incremental data.
    """
    global _agent_jsonl_map, _jsonl_map_refresh_ts
    _jsonl_map_refresh_ts = time.time()

    import glob as _glob
    jsonl_files = _glob.glob(str(CLAUDE_PROJECTS_DIR / "*" / "*.jsonl"))
    # Sort by mtime descending — most recent first
    jsonl_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

    seen_agents: set[str] = set()
    new_map: dict[str, str] = {}

    for fpath in jsonl_files:
        # Skip subagent files and old files (>24h)
        if "/subagents/" in fpath:
            continue
        try:
            age = time.time() - os.path.getmtime(fpath)
            if age > 86400:  # skip files older than 24h
                continue
            with open(fpath) as fh:
                first_line = fh.readline()
                if not first_line.strip():
                    continue
                d = json.loads(first_line)
                agent = d.get("agentSetting", "")
                if agent and agent not in seen_agents:
                    new_map[agent] = fpath
                    seen_agents.add(agent)
        except (OSError, json.JSONDecodeError):
            continue

    # Also scan remote machines for their agent JSONL files
    for machine_name, machine_cfg in _machines_config.items():
        ssh_target = machine_cfg.get("ssh_target", "")
        if not ssh_target:
            continue
        try:
            # Find recent JSONL files on remote machine, extract agent names
            cmd = (
                f"python3 -c \""
                f"import json,os,glob,time; now=time.time(); "
                f"files=glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl')); "
                f"recent=[(f,os.path.getmtime(f)) for f in files if now-os.path.getmtime(f)<86400 and '/subagents/' not in f]; "
                f"recent.sort(key=lambda x:-x[1]); "
                f"seen=set(); "
                f"[print(json.dumps({{'agent':json.loads(open(f).readline()).get('agentSetting',''),'path':f}})) "
                f"for f,_ in recent[:20] "
                f"if json.loads(open(f).readline()).get('agentSetting','') and "
                f"json.loads(open(f).readline()).get('agentSetting','') not in seen and "
                f"not seen.add(json.loads(open(f).readline()).get('agentSetting',''))]"
                f"\""
            )
            ssh_args = machine_cfg.get("ssh_args", [])
            r = subprocess.run(
                ["ssh"] + ssh_args + [ssh_target, cmd],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    try:
                        info = json.loads(line)
                        agent = info.get("agent", "")
                        remote_path = info.get("path", "")
                        if agent and agent not in seen_agents and remote_path:
                            # Store as "ssh://target:path" for remote scanning
                            new_map[agent] = f"ssh://{ssh_target}:{remote_path}"
                            seen_agents.add(agent)
                    except json.JSONDecodeError:
                        continue
        except (subprocess.SubprocessError, OSError) as e:
            warn(f"Remote JSONL scan failed for {machine_name}: {e}")

    _agent_jsonl_map = new_map
    if new_map:
        log(f"Token JSONL map refreshed: {', '.join(f'{k}={os.path.basename(v)[:12]}' for k,v in new_map.items())}")


def _scan_jsonl_incremental(fpath: str, agent_models: dict[str, str],
                             agent_name: str) -> dict | None:
    """
    Read new assistant messages from a JSONL file since last offset.
    Supports local files and remote files via ssh:// prefix.
    Returns aggregated token usage dict or None if no new data.
    """
    global _jsonl_offsets

    if fpath.startswith("ssh://"):
        return _scan_jsonl_remote(fpath, agent_models, agent_name)

    try:
        file_size = os.path.getsize(fpath)
    except OSError:
        return None

    last_offset = _jsonl_offsets.get(fpath, 0)
    if file_size <= last_offset:
        return None  # no new data

    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    msg_count = 0
    model_seen = ""

    try:
        with open(fpath) as fh:
            fh.seek(last_offset)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if d.get("type") != "assistant":
                    continue

                msg = d.get("message", {})
                if not isinstance(msg, dict):
                    continue

                usage = msg.get("usage", {})
                if not usage:
                    continue

                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)
                total_cache_read += usage.get("cache_read_input_tokens", 0)
                total_cache_create += usage.get("cache_creation_input_tokens", 0)
                model_seen = msg.get("model", model_seen)
                msg_count += 1

            _jsonl_offsets[fpath] = fh.tell()
    except OSError:
        return None

    if msg_count == 0:
        return None

    return _compute_cost(total_input, total_output, total_cache_read,
                         msg_count, model_seen, agent_models, agent_name)


def _scan_jsonl_remote(fpath: str, agent_models: dict[str, str],
                        agent_name: str) -> dict | None:
    """Scan a remote JSONL file via SSH. fpath format: ssh://target:path"""
    global _jsonl_offsets

    # Parse ssh://target:path
    rest = fpath[6:]  # strip "ssh://"
    colon_idx = rest.index(":")
    ssh_target = rest[:colon_idx]
    remote_path = rest[colon_idx + 1:]

    last_offset = _jsonl_offsets.get(fpath, 0)

    # Use tail -c + to read from byte offset, then parse assistant messages
    cmd = (
        f"python3 -c \""
        f"import json,os,sys; "
        f"f=open('{remote_path}'); f.seek({last_offset}); "
        f"ti=to=cr=cc=mc=0; ms=''; "
        f"[("
        f"  setattr(sys,'_d',json.loads(l)),"
        f"  (ti:=ti+sys._d.get('message',{{}}).get('usage',{{}}).get('input_tokens',0),"
        f"   to:=to+sys._d.get('message',{{}}).get('usage',{{}}).get('output_tokens',0),"
        f"   cr:=cr+sys._d.get('message',{{}}).get('usage',{{}}).get('cache_read_input_tokens',0),"
        f"   mc:=mc+1) if sys._d.get('type')=='assistant' and sys._d.get('message',{{}}).get('usage') else None"
        f") for l in f if l.strip()]; "
        f"print(json.dumps({{'in':ti,'out':to,'cr':cr,'mc':mc,'off':f.tell(),"
        f"'model':''}}))  "
        f"\""
    )

    try:
        r = subprocess.run(
            ["ssh", ssh_target, cmd],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return None

        data = json.loads(r.stdout.strip().splitlines()[-1])
        if data["mc"] == 0:
            return None

        _jsonl_offsets[fpath] = data["off"]
        return _compute_cost(
            data["in"], data["out"], data["cr"],
            data["mc"], data.get("model", ""),
            agent_models, agent_name,
        )
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None


def _compute_cost(total_input: int, total_output: int, total_cache_read: int,
                   msg_count: int, model_seen: str,
                   agent_models: dict[str, str], agent_name: str) -> dict:
    """Compute token cost and return usage dict."""
    if "opus" in model_seen:
        rate_key = "opus"
    else:
        model_key = agent_models.get(agent_name, "sonnet")
        rate_key = "opus" if "opus" in model_key else "sonnet"
    rates = COST_RATES.get(rate_key, COST_RATES["sonnet"])

    cost = (
        total_input * rates["input"]
        + total_output * rates["output"]
        + total_cache_read * rates["cache_read"]
    )

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_tokens": total_cache_read,
        "cost_usd": cost,
        "msg_count": msg_count,
    }


def scan_tokens_for_agent(
    state: AgentState, conn: sqlite3.Connection, agent_models: dict[str, str]
) -> None:
    """
    Read token usage from agent's JSONL conversation file.
    Falls back to pane-scraping for context percentage only.
    """
    global _jsonl_map_refresh_ts

    # Refresh JSONL map periodically
    if time.time() - _jsonl_map_refresh_ts >= JSONL_MAP_REFRESH_S:
        _refresh_agent_jsonl_map()

    # Get context % from pane (cheap, still useful)
    ctx_pct = 0.0
    output = capture_pane(state.pane_id, lines=10)
    if output:
        for line in output.splitlines():
            m = TOKEN_PATTERNS[1].search(line)  # ctx:XX% pattern
            if m:
                ctx_pct = float(m.group(1))
                break

    # Scan JSONL for actual token data
    jsonl_path = _agent_jsonl_map.get(state.name)
    if not jsonl_path:
        return

    result = _scan_jsonl_incremental(jsonl_path, agent_models, state.name)
    if not result:
        return

    db_upsert_token_usage(
        conn,
        state.name,
        result["input_tokens"],
        result["output_tokens"],
        result["cache_tokens"],
        result["cost_usd"],
        ctx_pct,
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

    # Log spend but do NOT enforce cap — CEO wants tracking only, no pausing
    if total >= SPEND_CAP_USD:
        log(f"SPEND TRACKING: ${total:.2f} >= ${SPEND_CAP_USD:.2f} (cap disabled, tracking only)", "WARN")
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

    # Load machine assignments from TOML (reuse shared loader)
    machine_map: dict[str, str] = {
        a["name"]: a.get("machine", "local")
        for a in _load_toml_agents()
        if "name" in a
    }

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

    # Initialize JSONL-based token tracking map
    _refresh_agent_jsonl_map()

    last_token_scan = 0.0
    last_spend_check = 0.0
    last_idle_check = 0.0
    last_queue_check = 0.0

    # Start inbox watcher thread for idle-wake
    inbox_watcher = InboxWatcherThread(agent_states, conn, dry_run=dry_run)
    inbox_watcher.start()
    log("[idle] InboxWatcherThread started")

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

            # -- Process wake queue from InboxWatcherThread
            for agent_name, trigger in inbox_watcher.get_pending_wakes():
                ws = agent_states.get(agent_name)
                if ws and ws.status == "idle_shutdown":
                    wake_agent(ws, conn, trigger=trigger, dry_run=dry_run)

            # -- Idle detection (every IDLE_CHECK_INTERVAL_S, not every 30s)
            run_idle_check = (now - last_idle_check >= IDLE_CHECK_INTERVAL_S)
            if run_idle_check:
                last_idle_check = now

            # -- Per-agent checks
            for name, state in list(agent_states.items()):
                if not state.pane_id:
                    continue

                # Skip all checks for idle-shutdown agents (they're not crashed)
                if state.status == "idle_shutdown":
                    continue

                # Auto-restart
                restarted = maybe_restart_agent(state, conn, dry_run=dry_run)

                # Post-restart: inject memory re-read P1 (after boot delay)
                if restarted and not dry_run:
                    # The memory re-read will be injected after the audit delay
                    # (scheduled in maybe_restart_agent via _pending_memory_audits)
                    pass

                # Context budget monitor (early compact at 70%)
                context_compacted = check_context_budget(
                    state, conn, dry_run=dry_run
                )

                # Auto-compact (includes pre-compact save injection)
                # Skip if context budget already triggered compact
                if not context_compacted:
                    maybe_compact_agent(state, conn, dry_run=dry_run)

                # Auto-continue
                maybe_continue_agent(state, conn, dry_run=dry_run)

                # Idle detection -- check if agent should be shutdown
                if run_idle_check and is_agent_idle(state):
                    if is_hot_period():
                        log(f"[{name}] Hot period active -- idle shutdown suppressed")
                    else:
                        idle_shutdown_agent(state, conn, dry_run=dry_run)

            # -- Memory audit checks (pending from restarts/compacts)
            check_pending_memory_audits(agent_states, conn, dry_run=dry_run)

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

            # -- Queue depth check -- every 120s
            if now - last_queue_check >= QUEUE_CHECK_INTERVAL_S:
                check_queue_depth(dry_run=dry_run)
                last_queue_check = now

        except Exception as e:
            err(f"Guardian loop error (iteration {iteration}): {e}")

        if once:
            break

        # Sleep in small increments so SIGTERM is responsive
        for _ in range(MAIN_INTERVAL_S * 2):  # 30s in 0.5s steps
            if not _running:
                break
            time.sleep(0.5)

    # Stop inbox watcher thread
    inbox_watcher.stop()
    inbox_watcher.join(timeout=10)
    log("[idle] InboxWatcherThread stopped")

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
