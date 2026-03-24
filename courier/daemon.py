"""Soul Courier — single daemon managing message delivery for all agents.

The CourierDaemon is the main orchestrator. It watches agent inbox
directories for new messages, formats them, injects them into tmux
panes, and manages retry queues, health checks, and CEO notifications.

All paths are derived from environment variables or Path.home() so the
daemon works on any machine without hardcoded paths.
"""

import fcntl
import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer

from soul_courier.formatter import MessageFormatter
from soul_courier.pane import PaneManager
from soul_courier.queue import MessageQueue
from soul_courier.watcher import InboxWatcher

log = logging.getLogger("soul-courier")

TEAM_NAME = os.environ.get("SOUL_TEAM_NAME", "soul-team")
TEAM_DIR = Path.home() / ".clawteam" / "teams" / TEAM_NAME
PANES_FILE = TEAM_DIR / "panes.json"
NATIVE_INBOX_DIR = Path.home() / ".claude" / "teams" / TEAM_NAME / "inboxes"

# Configurable path for CEO action queue file.
# Default: ~/soul-roles/shared/briefs/ceo-action-queue.md
ACTION_QUEUE_DIR = Path(
    os.environ.get("SOUL_ACTION_QUEUE_DIR", str(Path.home() / "soul-roles" / "shared" / "briefs"))
)


class CourierDaemon:
    def __init__(
        self,
        team_dir: Path = TEAM_DIR,
        panes_file: Path = PANES_FILE,
        dry_run: bool = False,
    ):
        self.team_dir = team_dir
        self.panes_file = panes_file
        self.dry_run = dry_run
        self._running = False

        # Load panes
        panes = self._load_panes()
        self.pane_mgr = PaneManager(panes)
        self.queue = MessageQueue(team_dir / "queue")
        self.queue.load()

        # Seen tracking -- per-agent sets for scoped deduplication
        self._sidecar_dir = team_dir / "sidecar"
        self._sidecar_dir.mkdir(parents=True, exist_ok=True)
        self._seen: dict[str, set[str]] = {}
        self._load_seen_logs()

        # Backoff tracking
        self._backoff: dict[str, float] = {}
        self._fail_count: dict[str, int] = {}
        self._last_drain: dict[str, float] = {}

        # CEO notification rate limiting (max 1 per agent per 10 min)
        self._last_ceo_notify: dict[str, float] = {}

        # Action queue for team-lead
        self._action_queue_path = ACTION_QUEUE_DIR / "ceo-action-queue.md"
        self._action_queue_lock = threading.Lock()

        # Observer
        self._observer: Optional[Observer] = None

    def _load_panes(self) -> dict[str, str]:
        """Read panes.json mapping agent names to tmux pane IDs."""
        try:
            return json.loads(self.panes_file.read_text())
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            log.error("Cannot read panes.json at %s", self.panes_file)
            return {}

    def _load_seen_logs(self) -> None:
        """Read per-agent seen logs from sidecar dir on startup."""
        for f in self._sidecar_dir.glob("*-seen.log"):
            agent = f.stem.replace("-seen", "")
            try:
                self._seen[agent] = set(f.read_text().splitlines())
            except OSError:
                self._seen[agent] = set()

    def _is_seen(self, agent: str, msg_file: Path) -> bool:
        """Check if a message has been seen by a specific agent.

        Seen tracking is per-agent so that a message in one agent's inbox
        being marked seen does not affect another agent's seen set.
        """
        msg_id = msg_file.stem
        return msg_id in self._seen.get(agent, set())

    def _mark_seen(self, msg_file: Path) -> None:
        """Mark a message as seen for its owning agent.

        Agent is derived from the inbox path. The msg_id is added to
        the in-memory set and appended to the on-disk seen log.
        """
        msg_id = msg_file.stem
        agent = self._agent_from_path(msg_file)
        if agent not in self._seen:
            self._seen[agent] = set()
        self._seen[agent].add(msg_id)
        # Append to seen log
        seen_log = self._sidecar_dir / f"{agent}-seen.log"
        try:
            with open(seen_log, "a") as f:
                f.write(msg_id + "\n")
        except OSError:
            log.warning("Cannot write seen log for %s", agent)

    def _agent_from_path(self, msg_file: Path) -> str:
        """Extract agent name from inbox path.

        Inbox dirs follow the pattern: inboxes/{agent}_{agent}/msg-*.json
        """
        parts = msg_file.parts
        for i, p in enumerate(parts):
            if p == "inboxes" and i + 1 < len(parts):
                dirname = parts[i + 1]
                return dirname.split("_")[0]
        return "unknown"

    def _archive(self, msg_file: Path) -> None:
        """Move a delivered message to its inbox's archive/ subdir."""
        archive_dir = msg_file.parent / "archive"
        archive_dir.mkdir(exist_ok=True)
        try:
            msg_file.rename(archive_dir / msg_file.name)
        except OSError:
            log.warning("Cannot archive %s", msg_file)

    def _mirror_native(self, msg_file: Path, agent: str) -> None:
        """Mirror message to native inbox (team-lead only).

        Writes JSON array format matching existing convention.
        Uses file locking to prevent corruption from concurrent writes.
        """
        if agent != "team-lead":
            return

        native_file = NATIVE_INBOX_DIR / "team-lead.json"
        native_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = json.loads(msg_file.read_text())
            entry = {
                "from": raw.get("from", "unknown"),
                "text": raw.get("content", ""),
                "timestamp": raw.get(
                    "timestamp",
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
                "read": False,
            }
            mode = "r+" if native_file.exists() else "w"
            with open(native_file, mode) as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    if mode == "r+":
                        content = f.read()
                        msgs = json.loads(content) if content.strip() else []
                    else:
                        msgs = []
                    if not isinstance(msgs, list):
                        msgs = []
                    msgs.append(entry)
                    f.seek(0)
                    f.truncate()
                    json.dump(msgs, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot mirror to native inbox: %s", msg_file.name)

    def _notify_ceo(self, agent: str, status: str) -> None:
        """Write crash/dead notification to CEO inbox via atomic rename."""
        # Never notify CEO about CEO's own pane
        if agent == "team-lead":
            return
        # Rate limit: max 1 notification per agent per 10 minutes
        now = time.time()
        last = self._last_ceo_notify.get(agent, 0)
        if now - last < 600:
            return
        self._last_ceo_notify[agent] = now

        ceo_inbox = self.team_dir / "inboxes" / "team-lead_team-lead"
        ceo_inbox.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        data = {
            "type": "status",
            "from": "courier",
            "to": "team-lead",
            "action": status,
            "agent": agent,
            "content": f"Agent {agent} pane is {status}.",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # Atomic write: write to tmp, then rename
        import tempfile as tf

        tmp = ceo_inbox / f".tmp-{ts}.json"
        target = ceo_inbox / f"msg-{ts}-courier-{agent}.json"
        tmp.write_text(json.dumps(data))
        tmp.rename(target)

    def _append_action_queue(self, data: dict) -> None:
        """Append an action item to the CEO action queue file."""
        summary = data.get("action_summary", data.get("content", "")[:80])
        from_user = data.get("from", "unknown")
        date = time.strftime("%b %d")
        line = f"- [ ] **{summary}** | From: {from_user} | Since: {date}\n"

        with self._action_queue_lock:
            if self._action_queue_path.exists():
                existing = self._action_queue_path.read_text()
                # Dedup: only check pending items (not resolved)
                pending_lines = [l for l in existing.splitlines() if l.startswith("- [ ]")]
                if any(summary in l for l in pending_lines):
                    return
                # Insert before ## Resolved section
                if "\n## Resolved" in existing:
                    existing = existing.replace(
                        "\n## Resolved", f"{line}\n## Resolved"
                    )
                else:
                    existing = existing.rstrip() + "\n" + line
                self._action_queue_path.write_text(existing)
            else:
                self._action_queue_path.parent.mkdir(parents=True, exist_ok=True)
                header = (
                    f"# CEO Action Queue\n"
                    f"*Last updated: {time.strftime('%Y-%m-%d %H:%M')}*\n\n"
                    f"## Pending\n{line}\n"
                    f"## Resolved\n"
                )
                self._action_queue_path.write_text(header)

    def _inject_action_reminder(self) -> None:
        """Inject a compact pending actions summary into team-lead pane."""
        with self._action_queue_lock:
            if not self._action_queue_path.exists():
                return
            lines = self._action_queue_path.read_text().splitlines()

        pending = [l for l in lines if l.startswith("- [ ]")]
        if not pending:
            return

        parts = [f"\u2501\u2501\u2501 {len(pending)} PENDING ACTIONS \u2501\u2501\u2501"]
        for i, item in enumerate(pending, 1):
            match = re.search(r'\*\*(.+?)\*\*', item)
            summary = match.group(1) if match else item[6:].split(" | ")[0]
            parts.append(f" {i}. {summary}")
        parts.append("\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

        reminder = "\n".join(parts)
        lock = self.pane_mgr.locks.get("team-lead")
        if lock:
            with lock:
                if not self.pane_mgr.inject("team-lead", reminder):
                    log.warning("Failed to inject action reminder into team-lead pane")
        else:
            log.warning("No pane lock for team-lead -- skipping action reminder")

    def _reminder_loop(self) -> None:
        """Periodically remind team-lead of pending action items."""
        # Fire once on startup
        self._inject_action_reminder()
        while self._running:
            # Sleep in smaller increments for clean shutdown
            for _ in range(180):  # 30 min = 180 * 10s
                if not self._running:
                    return
                time.sleep(10)
            self._inject_action_reminder()

    def _deliver(self, agent: str, msg_file: Path) -> bool:
        """Deliver a single message to an agent's tmux pane.

        Core delivery logic:
        1. Detect pane state
        2. Handle P1 interrupt if urgent + busy
        3. Format and inject message
        4. Verify injection
        5. Archive + mark seen on success
        6. Queue on failure with backoff
        """
        if not msg_file.exists():
            return False

        state = self.pane_mgr.detect_state(agent)
        try:
            msg_data = json.loads(msg_file.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot read message %s", msg_file)
            return False
        priority = msg_data.get("key", "normal")

        # P1 interrupt
        if priority == "urgent" and state == "busy":
            state = self._p1_interrupt(agent)

        lock = self.pane_mgr.locks.get(agent)
        if not lock:
            self.queue.add(agent, msg_file)
            return False

        with lock:
            if state in ("idle", "crunched"):
                is_crunched = state == "crunched"
                if priority == "urgent":
                    text = MessageFormatter.format_p1(msg_file, agent)
                else:
                    text = MessageFormatter.format(
                        msg_file, agent, is_crunched=is_crunched
                    )

                if not self.dry_run and self.pane_mgr.inject(agent, text):
                    from_user = msg_data.get("from", "unknown")
                    # Use [from_user] as fragment -- works for all format variants
                    fragment = f"[{from_user}]"
                    if self.pane_mgr.verify_injection(agent, fragment):
                        self._archive(msg_file)
                        self._mark_seen(msg_file)
                        self._mirror_native(msg_file, agent)
                        self._backoff.pop(agent, None)
                        self._fail_count.pop(agent, None)
                        # Track action items for team-lead
                        if agent == "team-lead" and msg_data.get("action_required"):
                            self._append_action_queue(msg_data)
                        log.info("Delivered to %s: %s", agent, msg_file.name)
                        return True

                # Failed injection or dry_run
                self.queue.add(agent, msg_file)
                self._increment_fail(agent)
                return False

            # Not idle -- queue the message
            self.queue.add(agent, msg_file)
            if state == "crashed":
                self._notify_ceo(agent, "crashed")
            elif state == "dead":
                self._notify_ceo(agent, "dead")
            self._mirror_native(msg_file, agent)
            return False

    def _p1_interrupt(self, agent: str) -> str:
        """Send Ctrl+C to interrupt a busy agent for P1 messages.

        Has a 30s cooldown per agent to prevent interrupt storms.
        Tries up to 3 times with 2s sleep between attempts.
        """
        lock_file = self._sidecar_dir / f"{agent}-interrupt.lock"
        if lock_file.exists():
            try:
                age = time.time() - lock_file.stat().st_mtime
                if age < 30:
                    return "busy"
            except OSError:
                pass

        pane_id = self.pane_mgr.panes.get(agent)
        if not pane_id:
            return "dead"

        for _ in range(3):
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "C-c"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(2)
            self.pane_mgr.invalidate_cache(agent)
            state = self.pane_mgr.detect_state(agent)
            if state in ("idle", "crunched"):
                lock_file.touch()
                return state
        return "busy"

    def _increment_fail(self, agent: str) -> None:
        """Track delivery failures with exponential backoff.

        Backoff starts at 10s and doubles each failure, capped at 120s.
        Every 5th consecutive failure notifies the CEO.
        """
        count = self._fail_count.get(agent, 0) + 1
        self._fail_count[agent] = count
        self._backoff[agent] = min(10 * (2 ** (count - 1)), 120)
        if count >= 5 and count % 5 == 0:
            log.warning("%d consecutive failures for %s", count, agent)
            self._notify_ceo(agent, f"delivery-failing ({count} attempts)")

    # -- Catch-up ---------------------------------------------------------

    def catchup(self) -> None:
        """Scan all inboxes for unseen messages and attempt delivery.

        Called once at startup to process any messages that arrived
        while the daemon was not running.
        """
        inboxes_dir = self.team_dir / "inboxes"
        count = 0
        for agent_dir in sorted(inboxes_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name == "agent":
                continue
            agent = agent_dir.name.split("_")[0]
            for msg in sorted(agent_dir.glob("msg-*.json")):
                if not self._is_seen(agent, msg):
                    self._deliver(agent, msg)
                    count += 1
        log.info("Catch-up complete: %d messages processed", count)

    # -- Queue Drainer ----------------------------------------------------

    def _drain_loop(self) -> None:
        """Periodically retry queued messages with exponential backoff.

        Runs every 10s. Includes overflow batching: if 3+ discussion
        messages from the same thread are queued, they are batched
        into a single summary injection.
        """
        while self._running:
            for agent in self.queue.agents_with_messages():
                backoff = self._backoff.get(agent, 0)
                last = self._last_drain.get(agent, 0)
                if time.monotonic() - last < backoff:
                    continue
                self._last_drain[agent] = time.monotonic()

                # Overflow batching: check for 3+ discussion msgs from same thread
                batch = self.queue.peek_thread_batch(agent, min_count=3)
                if batch:
                    thread_id, files = batch
                    state = self.pane_mgr.detect_state(agent)
                    if state in ("idle", "crunched"):
                        text = MessageFormatter.format_batch(thread_id, files, agent)
                        with self.pane_mgr.locks.get(agent, threading.Lock()):
                            if self.pane_mgr.inject(agent, text):
                                for f in files:
                                    self.queue.remove(agent, f)
                                    self._archive(f)
                                    self._mark_seen(f)
                                continue

                msg = self.queue.pop(agent)
                if msg and msg.exists():
                    self._deliver(agent, msg)
                elif msg:
                    log.warning("Queued file missing: %s", msg)
            time.sleep(10)

    # -- Health Checker ---------------------------------------------------

    def _health_loop(self) -> None:
        """Run health checks every 60s."""
        while self._running:
            time.sleep(60)
            try:
                self._run_health_check()
            except Exception:
                log.exception("Health check failed")

    def _run_health_check(self) -> None:
        """Validate pane liveness, restart observer if needed.

        Uses `tmux list-panes -s -t <team>` to get all panes across
        all windows in the session, then marks dead agents and revives
        any that reappeared.
        """
        # Reload panes
        new_panes = self._load_panes()
        if not new_panes:
            return

        # Get live tmux panes (the -s flag lists all windows in session)
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "list-panes",
                    "-s",
                    "-t",
                    TEAM_NAME,
                    "-F",
                    "#{pane_id}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            live_panes = set(result.stdout.strip().splitlines())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log.warning("Cannot list tmux panes")
            return

        # Mark dead agents, revive returning ones
        for agent, pane_id in new_panes.items():
            if pane_id not in live_panes:
                log.warning("Agent %s pane %s is dead", agent, pane_id)
                self.pane_mgr.mark_dead(agent)
            elif agent in self.pane_mgr._dead_agents:
                # Revived
                self.pane_mgr._dead_agents.discard(agent)

        self.pane_mgr.update_panes(
            {a: p for a, p in new_panes.items() if p in live_panes}
        )

        # Verify observer is alive
        if self._observer and not self._observer.is_alive():
            log.warning("Watchdog observer died -- restarting")
            self._start_observer()

        # Flush queues
        self.queue.flush()

        log.info("Health check OK: %d active agents", len(self.pane_mgr.panes))

    # -- Observer ---------------------------------------------------------

    def _start_observer(self) -> None:
        """Start (or restart) the watchdog filesystem observer."""
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)

        inboxes_dir = self.team_dir / "inboxes"
        handler = InboxWatcher(callback=self._on_new_message)
        self._observer = Observer()
        self._observer.schedule(handler, str(inboxes_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        log.info("Watchdog observer started on %s", inboxes_dir)

    def _on_new_message(self, agent: str, msg_file: Path) -> None:
        """Callback from InboxWatcher on new message detection."""
        if self._is_seen(agent, msg_file):
            return
        time.sleep(0.2)  # Brief delay for file to be fully written
        self._deliver(agent, msg_file)

    # -- Lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Start the courier daemon: catchup, observer, drain, health threads."""
        log.info("Soul Courier starting (team=%s)", TEAM_NAME)
        self._running = True

        # Catch-up
        self.catchup()
        self.queue.flush()

        # Start observer
        self._start_observer()

        # Start drain thread
        drain_thread = threading.Thread(
            target=self._drain_loop, name="drain", daemon=True
        )
        drain_thread.start()

        # Start health thread
        health_thread = threading.Thread(
            target=self._health_loop, name="health", daemon=True
        )
        health_thread.start()

        # Queue auto-flush
        def flush_loop():
            while self._running:
                time.sleep(30)
                self.queue.flush()

        flush_thread = threading.Thread(
            target=flush_loop, name="flush", daemon=True
        )
        flush_thread.start()

        # Start action reminder thread (30-min reminders for team-lead)
        reminder_thread = threading.Thread(
            target=self._reminder_loop, name="reminder", daemon=True
        )
        reminder_thread.start()

        log.info("Soul Courier running -- %d agents", len(self.pane_mgr.panes))

        # Block main thread
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        """Gracefully stop the courier daemon."""
        log.info("Soul Courier stopping...")
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        self.queue.flush()
        log.info("Soul Courier stopped.")
