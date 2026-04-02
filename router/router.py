#!/usr/bin/env python3
"""
soul-router.py — Central message router for soul-team.
Handles broadcast fan-out and group discussion thread management.
Watches ~/.clawteam/teams/soul-team/{broadcast,discussions}/ via watchdog.
All agents' inboxes use doubled naming: {agent}_{agent}/
"""

import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Timer

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ── Config ────────────────────────────────────────────────────────────────────
TEAM_DIR = Path.home() / ".clawteam" / "teams" / "soul-team"
INBOXES_DIR = TEAM_DIR / "inboxes"
BROADCAST_DIR = TEAM_DIR / "broadcast"
DISCUSSIONS_DIR = TEAM_DIR / "discussions"
SIDECAR_DIR = TEAM_DIR / "sidecar"

ALL_AGENTS = [
    "happy", "xavier", "hawkeye", "pepper",
    "fury", "loki", "shuri", "stark", "banner",
]

MAX_MESSAGES_PER_THREAD = 20
MAX_CONCURRENT_DISCUSSIONS = 3
FAN_OUT_COOLDOWN_SECS = 10  # batch fan-outs within this window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [router] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("soul-router")


def ensure_dirs():
    """Create all required directories."""
    for d in [TEAM_DIR, INBOXES_DIR, BROADCAST_DIR, DISCUSSIONS_DIR, SIDECAR_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    for agent in ALL_AGENTS + ["team-lead"]:
        inbox = INBOXES_DIR / f"{agent}_{agent}"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "archive").mkdir(exist_ok=True)


def slugify(text: str) -> str:
    """Convert topic to a filesystem-safe thread_id slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:60]  # cap length


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_to_inbox(agent: str, msg: dict, msg_filename: str = None) -> bool:
    """Write a message dict to an agent's inbox directory."""
    inbox = INBOXES_DIR / f"{agent}_{agent}"
    inbox.mkdir(parents=True, exist_ok=True)
    if msg_filename is None:
        ts = int(time.time())
        msg_filename = f"{ts}-router.json"
    dest = inbox / msg_filename
    try:
        with open(dest, "w") as f:
            json.dump(msg, f, indent=2)
        log.info(f"→ inbox/{agent}_{agent}/{msg_filename}")
        return True
    except Exception as e:
        log.error(f"Failed to write to {agent} inbox: {e}")
        return False


def load_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to read {path}: {e}")
        return None


def save_json(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


# ── Fanned message ID tracking (per thread, in memory) ───────────────────────
_fanned_ids: dict[str, set] = {}
_fanned_lock = Lock()


def is_fanned(thread_id: str, msg_id: str) -> bool:
    with _fanned_lock:
        return msg_id in _fanned_ids.get(thread_id, set())


def mark_fanned(thread_id: str, msg_id: str):
    with _fanned_lock:
        if thread_id not in _fanned_ids:
            _fanned_ids[thread_id] = set()
        _fanned_ids[thread_id].add(msg_id)


# ── Fan-out cooldown batch state ──────────────────────────────────────────────
_pending_fanouts: dict[str, list] = {}  # thread_id → list of (msg, filename, sender)
_fanout_timers: dict[str, Timer] = {}
_fanout_lock = Lock()


def schedule_fanout(thread_id: str, msg: dict, filename: str, sender: str):
    """Batch fan-outs within FAN_OUT_COOLDOWN_SECS window."""
    with _fanout_lock:
        if thread_id not in _pending_fanouts:
            _pending_fanouts[thread_id] = []
        _pending_fanouts[thread_id].append((msg, filename, sender))

        # Cancel existing timer if any
        if thread_id in _fanout_timers:
            _fanout_timers[thread_id].cancel()

        # Schedule delivery after cooldown
        t = Timer(FAN_OUT_COOLDOWN_SECS, _flush_fanout, args=[thread_id])
        _fanout_timers[thread_id] = t
        t.daemon = True
        t.start()
        log.debug(f"Scheduled fan-out for thread {thread_id} in {FAN_OUT_COOLDOWN_SECS}s")


def _flush_fanout(thread_id: str):
    with _fanout_lock:
        batch = _pending_fanouts.pop(thread_id, [])
        _fanout_timers.pop(thread_id, None)

    if not batch:
        return

    log.info(f"Flushing {len(batch)} message(s) for thread {thread_id}")

    state_path = DISCUSSIONS_DIR / thread_id / "state.json"
    state = load_json(state_path)
    if not state:
        log.warning(f"Thread {thread_id} has no state.json — skipping fan-out")
        return

    if state.get("status") == "closed":
        log.info(f"Thread {thread_id} is closed — skipping fan-out")
        return

    participants = state.get("participants", ALL_AGENTS)

    for msg, filename, sender in batch:
        msg_id = msg.get("id", filename)
        if is_fanned(thread_id, msg_id):
            continue

        # Fan out to all participants EXCEPT the sender
        recipients = [p for p in participants if p != sender and p != "team-lead"] + \
                     (["team-lead"] if sender != "team-lead" else [])
        recipients = [r for r in recipients if r != sender]

        for agent in recipients:
            fan_msg = dict(msg)
            fan_msg["to"] = agent
            ts = int(time.time())
            write_to_inbox(agent, fan_msg, f"{ts}-{sender}.json")

        mark_fanned(thread_id, msg_id)

        # Update message count in state
        state["message_count"] = state.get("message_count", 0) + 1
        save_json(state_path, state)

        # Auto-close if limit reached
        if state["message_count"] >= MAX_MESSAGES_PER_THREAD:
            log.warning(f"Thread {thread_id} reached {MAX_MESSAGES_PER_THREAD} messages — auto-closing")
            _close_thread(thread_id, state, "Thread limit reached. CEO: review and decide.")


def _close_thread(thread_id: str, state: dict, reason: str):
    """Close a thread and notify all participants."""
    state_path = DISCUSSIONS_DIR / thread_id / "state.json"
    state["status"] = "closed"
    save_json(state_path, state)

    close_msg = {
        "id": f"msg-{int(time.time())}-router",
        "from": "router",
        "to": "team-lead",
        "type": "group-discussion",
        "thread_id": thread_id,
        "content": f"[Thread closed] {reason}",
        "ts": utcnow(),
    }
    participants = state.get("participants", ALL_AGENTS) + ["team-lead"]
    for agent in participants:
        close_msg_copy = dict(close_msg)
        close_msg_copy["to"] = agent
        ts = int(time.time())
        write_to_inbox(agent, close_msg_copy, f"{ts}-close.json")

    log.info(f"Thread {thread_id} closed: {reason}")


def count_active_discussions() -> int:
    count = 0
    for thread_dir in DISCUSSIONS_DIR.iterdir():
        if not thread_dir.is_dir():
            continue
        state_path = thread_dir / "state.json"
        state = load_json(state_path)
        if state and state.get("status") == "active":
            count += 1
    return count


# ── Broadcast handler ─────────────────────────────────────────────────────────
class BroadcastHandler(FileSystemEventHandler):
    def __init__(self):
        self._seen: set = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".json" or path.name in self._seen:
            return
        self._seen.add(path.name)
        time.sleep(0.2)  # ensure file is fully written
        self._handle_broadcast(path)

    def on_moved(self, event):
        """Handle atomic temp→final renames (clawteam inbox send uses this pattern)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix != ".json" or path.name in self._seen:
            return
        self._seen.add(path.name)
        self._handle_broadcast(path)

    def _handle_broadcast(self, path: Path):
        msg = load_json(path)
        if not msg:
            return
        log.info(f"Broadcast: {path.name} from {msg.get('from', 'unknown')}")
        ts = int(time.time())
        for agent in ALL_AGENTS:
            fan_msg = dict(msg)
            fan_msg["to"] = agent
            fan_msg["type"] = "broadcast"
            write_to_inbox(agent, fan_msg, f"{ts}-broadcast.json")
        log.info(f"Broadcast fanned out to {len(ALL_AGENTS)} agents")


# ── Discussion handler ────────────────────────────────────────────────────────
class DiscussionHandler(FileSystemEventHandler):
    """Watches the top-level discussions/ dir for creation requests and thread responses."""

    def __init__(self):
        self._seen_top: set = set()
        self._watched_threads: set = set()
        self._thread_observers: dict = {}

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".json":
            return
        # Only handle files directly in discussions/ (not in subdirs)
        if path.parent != DISCUSSIONS_DIR:
            return
        if path.name in self._seen_top:
            return
        self._seen_top.add(path.name)
        time.sleep(0.2)
        self._handle_request(path)

    def on_moved(self, event):
        """Handle atomic temp→final renames (clawteam uses this pattern)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix != ".json":
            return
        if path.parent != DISCUSSIONS_DIR:
            return
        if path.name in self._seen_top:
            return
        self._seen_top.add(path.name)
        self._handle_request(path)

    def _handle_request(self, path: Path):
        msg = load_json(path)
        if not msg:
            return
        action = msg.get("action")
        if action == "create":
            self._create_thread(msg)
        elif action == "close":
            self._close_thread_request(msg)
        else:
            log.warning(f"Unknown action in {path.name}: {action}")

    def _create_thread(self, msg: dict):
        topic = msg.get("topic", "discussion")
        content = msg.get("content", "")
        sender = msg.get("from", "team-lead")
        date_str = datetime.now().strftime("%Y-%m-%d")
        thread_id = f"{slugify(topic)}-{date_str}"

        # Check concurrent discussion limit
        active = count_active_discussions()
        if active >= MAX_CONCURRENT_DISCUSSIONS:
            log.warning(f"Max concurrent discussions ({MAX_CONCURRENT_DISCUSSIONS}) reached")
            warn_msg = {
                "id": f"msg-{int(time.time())}-router",
                "from": "router",
                "to": "team-lead",
                "type": "direct",
                "content": f"Cannot create discussion '{topic}': {active} discussions already active. Close one first.",
                "ts": utcnow(),
            }
            write_to_inbox("team-lead", warn_msg, f"{int(time.time())}-router.json")
            return

        # Determine participants
        raw_participants = msg.get("participants", ["all"])
        if raw_participants == ["all"] or "all" in raw_participants:
            participants = ALL_AGENTS[:]
        else:
            participants = [p for p in raw_participants if p in ALL_AGENTS + ["team-lead"]]

        # Create thread directory
        thread_dir = DISCUSSIONS_DIR / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)

        # Write state.json
        ts_str = utcnow()
        state = {
            "thread_id": thread_id,
            "topic": topic,
            "participants": participants,
            "started_by": sender,
            "started_at": ts_str,
            "status": "active",
            "message_count": 0,
        }
        save_json(thread_dir / "state.json", state)

        # Write opening message
        ts = int(time.time())
        opening = {
            "id": f"msg-{ts}-{sender}",
            "from": sender,
            "to": "all",
            "type": "group-discussion",
            "thread_id": thread_id,
            "content": content,
            "ts": ts_str,
        }
        save_json(thread_dir / f"{ts}-{sender}.json", opening)

        # Fan out opening message to all participants
        for agent in participants:
            fan_msg = dict(opening)
            fan_msg["to"] = agent
            write_to_inbox(agent, fan_msg, f"{ts}-{sender}.json")

        log.info(f"Created discussion {thread_id} for {len(participants)} participants")

        # Start watching this thread directory for responses
        self._watch_thread(thread_id)

    def _close_thread_request(self, msg: dict):
        thread_id = msg.get("thread_id")
        if not thread_id:
            log.warning("Close request missing thread_id")
            return
        state_path = DISCUSSIONS_DIR / thread_id / "state.json"
        state = load_json(state_path)
        if not state:
            log.warning(f"Cannot close unknown thread: {thread_id}")
            return
        _close_thread(thread_id, state, "Closed by CEO")

    def _watch_thread(self, thread_id: str):
        if thread_id in self._watched_threads:
            return
        self._watched_threads.add(thread_id)
        handler = ThreadResponseHandler(thread_id)
        observer = Observer()
        observer.schedule(handler, str(DISCUSSIONS_DIR / thread_id), recursive=False)
        observer.daemon = True
        observer.start()
        self._thread_observers[thread_id] = observer
        log.info(f"Watching thread directory: {thread_id}")


class ThreadResponseHandler(FileSystemEventHandler):
    """Watches a single thread directory for agent responses."""

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self._seen: set = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".json" or path.name == "state.json":
            return
        if path.name in self._seen:
            return
        self._seen.add(path.name)
        time.sleep(0.2)
        self._handle_response(path)

    def on_moved(self, event):
        """Handle atomic temp→final renames (clawteam uses this pattern)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix != ".json" or path.name == "state.json":
            return
        if path.name in self._seen:
            return
        self._seen.add(path.name)
        self._handle_response(path)

    def _handle_response(self, path: Path):
        msg = load_json(path)
        if not msg:
            return

        # Extract sender from filename: {timestamp}-{agent}.json
        parts = path.stem.split("-", 1)
        sender = parts[1] if len(parts) > 1 else msg.get("from", "unknown")

        log.info(f"Thread {self.thread_id}: response from {sender} ({path.name})")

        msg_id = msg.get("id", path.name)
        if is_fanned(self.thread_id, msg_id):
            log.debug(f"Skipping duplicate: {msg_id}")
            return

        # Ensure type and thread_id are set
        msg["type"] = "group-discussion"
        msg["thread_id"] = self.thread_id
        if "from" not in msg:
            msg["from"] = sender

        schedule_fanout(self.thread_id, msg, path.name, sender)


# ── Crash recovery: catch up on active threads ────────────────────────────────
def crash_recovery(disc_handler: DiscussionHandler):
    """On startup: resume watching all active threads and catch up on unfanned messages."""
    log.info("Running crash recovery scan...")
    recovered = 0
    for thread_dir in DISCUSSIONS_DIR.iterdir():
        if not thread_dir.is_dir():
            continue
        state_path = thread_dir / "state.json"
        state = load_json(state_path)
        if not state or state.get("status") != "active":
            continue
        thread_id = state["thread_id"]
        log.info(f"Resuming watch on active thread: {thread_id}")
        disc_handler._watch_thread(thread_id)

        # Check for unfanned messages: any response files not yet in fanned set
        last_fan_ts = 0
        for msg_file in sorted(thread_dir.glob("*.json")):
            if msg_file.name == "state.json":
                continue
            msg = load_json(msg_file)
            if not msg:
                continue
            msg_id = msg.get("id", msg_file.name)
            # Skip opening message from team-lead (already fanned at creation)
            if not is_fanned(thread_id, msg_id):
                parts = msg_file.stem.split("-", 1)
                sender = parts[1] if len(parts) > 1 else msg.get("from", "unknown")
                if sender != "team-lead" or state.get("message_count", 0) > 0:
                    log.info(f"Catch-up fan-out: {msg_file.name} in thread {thread_id}")
                    schedule_fanout(thread_id, msg, msg_file.name, sender)
                    recovered += 1

    log.info(f"Crash recovery complete: {recovered} unfanned messages scheduled")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("soul-router starting up")
    ensure_dirs()

    broadcast_handler = BroadcastHandler()
    disc_handler = DiscussionHandler()

    observer = Observer()
    observer.schedule(broadcast_handler, str(BROADCAST_DIR), recursive=False)
    observer.schedule(disc_handler, str(DISCUSSIONS_DIR), recursive=False)
    observer.start()
    log.info(f"Watching: {BROADCAST_DIR}")
    log.info(f"Watching: {DISCUSSIONS_DIR}")

    # Catch up on active threads from before restart
    crash_recovery(disc_handler)

    log.info("soul-router ready")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down...")
        observer.stop()
    observer.join()
    log.info("soul-router stopped")


if __name__ == "__main__":
    main()
