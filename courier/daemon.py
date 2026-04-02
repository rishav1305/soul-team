"""Soul Courier — Single daemon managing message delivery for all agents."""
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
from soul_courier.status import StatusStore
from soul_courier.watcher import InboxWatcher

log = logging.getLogger("soul-courier")

TEAM_NAME = os.environ.get("SOUL_TEAM_NAME", "soul-team")
MAX_RETRIES = int(os.environ.get("SOUL_COURIER_MAX_RETRIES", "10"))
TEAM_DIR = Path.home() / ".clawteam" / "teams" / TEAM_NAME
DND_FLAG = TEAM_DIR / "dnd-team-lead"
PANES_FILE = TEAM_DIR / "panes.json"
NATIVE_INBOX_DIR = Path.home() / ".claude" / "teams" / TEAM_NAME / "inboxes"

# Agents that receive messages via file only (no tmux pane injection).
# team-lead's hidden pane is a bare bash shell — injected text gets
# executed as commands. File-only delivery avoids this entirely.
FILE_ONLY_AGENTS = {"team-lead"}


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
        self.status = StatusStore(team_dir / "status")

        # Seen tracking — per-agent sets for scoped deduplication
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
        self._action_queue_path = Path.home() / "soul-roles" / "shared" / "briefs" / "ceo-action-queue.md"
        self._action_queue_lock = threading.Lock()

        # File-only delivery log for team-lead (human-readable message log)
        self._file_delivery_log = team_dir / "delivery-log-team-lead.jsonl"

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

        Seen tracking is per-agent so that a message in fury's inbox
        being marked seen does not affect hawkeye's seen set.
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

        Writes JSON array format matching existing soul-bridge convention.
        Uses file locking to prevent corruption from concurrent writes.
        """
        if agent != "team-lead":
            return
        import fcntl

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
                    f"*Last updated: {time.strftime('%Y-%m-%d %H:%M IST')}*\n\n"
                    f"## Pending\n{line}\n"
                    f"## Resolved\n"
                )
                self._action_queue_path.write_text(header)

    def _inject_action_reminder(self) -> None:
        """Write pending actions summary to delivery log (file-based, no pane injection).

        Previously injected into team-lead's tmux pane, which caused bash to
        execute the reminder text. Now writes to the JSONL delivery log and
        native inbox instead.
        """
        with self._action_queue_lock:
            if not self._action_queue_path.exists():
                return
            lines = self._action_queue_path.read_text().splitlines()

        pending = [l for l in lines if l.startswith("- [ ]")]
        if not pending:
            return

        parts = [f"━━━ {len(pending)} PENDING ACTIONS ━━━"]
        for i, item in enumerate(pending, 1):
            match = re.search(r'\*\*(.+?)\*\*', item)
            summary = match.group(1) if match else item[6:].split(" | ")[0]
            parts.append(f" {i}. {summary}")
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━")

        reminder = "\n".join(parts)
        # Write to delivery log instead of pane injection
        try:
            log_entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "from": "courier",
                "content": reminder,
                "priority": "info",
                "file": "action-reminder",
            }
            with open(self._file_delivery_log, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except OSError:
            log.warning("Failed to write action reminder to delivery log")

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

    def _deliver_file_only(self, agent: str, msg_file: Path) -> bool:
        """Deliver a message via file only — no tmux pane injection.

        Used for FILE_ONLY_AGENTS (e.g. team-lead) whose pane is a bare
        bash shell that would execute injected text as commands.

        Delivery path:
        1. Mirror to native inbox (JSON array for soul-bridge compat)
        2. Append to JSONL delivery log (human-readable audit trail)
        3. Archive + mark seen
        4. Track action items if flagged
        5. Send receipt to sender
        """
        if not msg_file.exists():
            return False

        try:
            msg_data = json.loads(msg_file.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot read message %s", msg_file)
            return False

        # Mirror to native inbox
        self._mirror_native(msg_file, agent)

        # Append to JSONL delivery log
        try:
            log_entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "from": msg_data.get("from", "unknown"),
                "content": msg_data.get("content", ""),
                "priority": msg_data.get("key", "normal"),
                "file": msg_file.name,
            }
            with open(self._file_delivery_log, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except OSError:
            log.warning("Cannot write delivery log for %s", msg_file.name)

        # Archive + mark seen
        self._archive(msg_file)
        self._mark_seen(msg_file)

        # Track action items
        if msg_data.get("action_required"):
            self._append_action_queue(msg_data)

        # Send receipt to sender
        sender = msg_data.get("from", "")
        if sender:
            self._send_receipt(sender, agent)

        self.status.record(agent, msg_file, "delivered", sender=sender)
        log.info("File-only delivery to %s: %s (from: %s)", agent, msg_file.name, sender)
        return True

    def _deliver(self, agent: str, msg_file: Path) -> bool:
        """Deliver a single message to an agent's tmux pane.

        Core delivery logic:
        1. Check DND for team-lead (queue silently if active)
        2. Detect pane state
        3. Handle P1 interrupt if urgent + busy
        4. Format and inject message
        5. Verify injection
        6. Archive + mark seen on success
        7. Queue on failure with backoff
        """
        if not msg_file.exists():
            return False

        # DND mode: check per-agent DND flag, queue silently if active
        agent_dnd_flag = TEAM_DIR / f"dnd-{agent}"
        if agent_dnd_flag.exists():
            self.queue.add(agent, msg_file)
            self.status.record(agent, msg_file, "queued")
            log.info("DND active — queued for %s: %s", agent, msg_file.name)
            return False

        state = self.pane_mgr.detect_state(agent)
        try:
            msg_data = json.loads(msg_file.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot read message %s", msg_file)
            return False

        # Org routing: domain leads (pepper, fury, loki, shuri) + xavier can message
        # team-lead directly. Leaf agents (happy, hawkeye, stark, banner) get
        # redirected to their domain lead. Nothing lost, just rerouted.
        # Skip redirect for courier-generated messages.
        if agent == "team-lead":
            sender = msg_data.get("from", "")
            is_courier_msg = "courier" in msg_file.name or msg_data.get("type") in ("receipt", "alert", "health")
            if not is_courier_msg:
                LEAF_TO_LEAD = {
                    "hawkeye": "loki",
                    "happy": "shuri",
                    "stark": "fury",
                    "banner": "fury",
                }
                redirect_to = LEAF_TO_LEAD.get(sender)
                if redirect_to:
                    redirect_inbox = self.team_dir / "inboxes" / f"{redirect_to}_{redirect_to}" / "new"
                    redirect_inbox.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(str(msg_file), str(redirect_inbox / msg_file.name))
                    self._archive(msg_file)
                    log.info("Org redirect: %s→team-lead copied to %s inbox", sender, redirect_to)
                    return True

        # File-only agents: skip pane injection entirely
        if agent in FILE_ONLY_AGENTS:
            return self._deliver_file_only(agent, msg_file)

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
                    # inject() succeeded — archive and mark seen immediately to prevent
                    # re-delivery loops. verify_injection is best-effort only: if the
                    # agent processes the message before the 2s verify window, the
                    # fragment may already be scrolled out of the captured pane content,
                    # causing a false-negative that would re-queue an already-delivered
                    # message (Friday / Loki re-delivery loop, Mar 24).
                    self._archive(msg_file)
                    self._mark_seen(msg_file)
                    self._mirror_native(msg_file, agent)
                    self._backoff.pop(agent, None)
                    self._fail_count.pop(agent, None)
                    # Track action items for team-lead
                    if agent == "team-lead" and msg_data.get("action_required"):
                        self._append_action_queue(msg_data)
                    # Send delivery receipt to sender's pane
                    sender = msg_data.get("from", "")
                    if sender:
                        self._send_receipt(sender, agent)
                    # Record delivered status
                    self.status.record(agent, msg_file, "delivered", sender=sender)
                    # Best-effort verify (log only — does NOT gate delivery)
                    from_user = msg_data.get("from", "unknown")
                    if not self.pane_mgr.verify_injection(agent, from_user):
                        log.warning(
                            "verify_injection miss for %s:%s (fragment=%r) — "
                            "message was injected and archived; agent processed it fast",
                            agent, msg_file.name, from_user,
                        )
                    else:
                        log.info("Delivered+verified to %s: %s", agent, msg_file.name)
                    return True

                # inject() itself failed or dry_run — queue for retry
                self.queue.add(agent, msg_file)
                self.status.record(agent, msg_file, "failed")
                self._increment_fail(agent, msg_file=msg_file)
                return False

            # Not idle — queue the message
            self.queue.add(agent, msg_file)
            self.status.record(agent, msg_file, "queued")
            if state == "dead":
                self._notify_ceo(agent, "dead")
            self._mirror_native(msg_file, agent)
            return False

    def _p1_interrupt(self, agent: str) -> str:
        """Send Ctrl+C to interrupt a busy agent for P1 messages.

        Has a 30s cooldown per agent to prevent interrupt storms.
        Tries up to 5 times with 3s sleep between attempts.
        After each C-c, sends an empty Enter to flush the shell prompt
        so the state detection can confirm idle more reliably.
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

        for attempt in range(5):
            log.debug("P1 interrupt attempt %d/5 for %s", attempt + 1, agent)
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "C-c"],
                capture_output=True,
                timeout=5,
            )
            # Brief pause then send Enter to flush shell prompt after C-c
            time.sleep(0.5)
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                capture_output=True,
                timeout=5,
            )
            time.sleep(2.5)
            self.pane_mgr.invalidate_cache(agent)
            state = self.pane_mgr.detect_state(agent)
            if state in ("idle", "crunched"):
                lock_file.touch()
                log.info("P1 interrupt succeeded for %s after %d attempt(s)", agent, attempt + 1)
                return state
        log.warning("P1 interrupt failed for %s after 5 attempts", agent)
        return "busy"

    def _send_receipt(self, sender: str, delivered_to: str) -> None:
        """Inject a delivery receipt into the sender's pane.

        Receipt is a single-line pane injection (not an inbox message).
        Skipped if sender == delivered_to, sender has no known pane,
        or sender is a FILE_ONLY_AGENT (receipt logged to file instead).
        """
        if sender == delivered_to:
            return
        # File-only agents: log receipt to delivery log instead of pane
        if sender in FILE_ONLY_AGENTS:
            try:
                log_entry = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "from": "courier",
                    "content": f"[COURIER] ✓ Delivered to {delivered_to}",
                    "priority": "receipt",
                    "file": "receipt",
                }
                with open(self._file_delivery_log, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except OSError:
                log.debug("Cannot write receipt to delivery log for %s→%s", sender, delivered_to)
            return
        if sender not in self.pane_mgr.panes:
            return
        receipt_text = f"\n[COURIER] ✓ Delivered to {delivered_to}\n"
        lock = self.pane_mgr.locks.get(sender)
        if lock:
            with lock:
                if not self.pane_mgr.inject(sender, receipt_text):
                    log.debug("Receipt inject failed for %s→%s", sender, delivered_to)
        else:
            if not self.pane_mgr.inject(sender, receipt_text):
                log.debug("Receipt inject failed for %s→%s (no lock)", sender, delivered_to)

    def _move_to_dlq(self, agent: str) -> None:
        """Move all queued messages for agent to the dead letter queue.

        Called when fail_count reaches MAX_RETRIES. Messages are moved
        (not copied) to team_dir/dlq/{agent}/ and the in-memory queue
        is drained. CEO is notified with a [DLQ] prefix.
        """
        dlq_dir = self.team_dir / "dlq" / agent
        dlq_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        while self.queue.has_messages(agent):
            msg = self.queue.pop(agent)
            if msg and msg.exists():
                try:
                    self.status.record(agent, msg, "dlq")
                    msg.rename(dlq_dir / msg.name)
                    moved += 1
                except OSError:
                    log.warning("Cannot move %s to DLQ", msg)
        log.error("[DLQ] %d message(s) for %s moved to dead letter queue", moved, agent)
        self._notify_ceo(agent, f"dlq ({moved} message(s) after {MAX_RETRIES} failed attempts)")

    def _increment_fail(self, agent: str, msg_file: Optional[Path] = None) -> None:
        """Track delivery failures with exponential backoff.

        Backoff starts at 5s and doubles each failure, capped at 30s.
        Notifies the CEO on the 1st failure and every 5th thereafter.
        After MAX_RETRIES, all pending messages are moved to the DLQ.

        msg_file is the message that failed — used to record status. When
        not supplied (e.g. called from health check), only fail-count and
        backoff are updated.
        """
        count = self._fail_count.get(agent, 0) + 1
        self._fail_count[agent] = count
        self._backoff[agent] = min(5 * (2 ** (count - 1)), 30)
        if count >= MAX_RETRIES:
            log.error("MAX_RETRIES (%d) reached for %s — moving to DLQ", MAX_RETRIES, agent)
            if msg_file:
                self.queue.add(agent, msg_file)
            self._move_to_dlq(agent)
            self._fail_count.pop(agent, None)
            self._backoff.pop(agent, None)
        elif count == 1 or (count >= 5 and count % 5 == 0):
            log.warning("%d consecutive failure(s) for %s", count, agent)
            self._notify_ceo(agent, f"delivery-failing ({count} attempt(s))")

    # -- Catch-up ---------------------------------------------------------

    def catchup(self) -> None:
        """Scan all inboxes for unseen messages and attempt delivery.

        Called once at startup to process any messages that arrived
        while the daemon was not running.

        Messages live in inboxes/{agent}_{agent}/new/msg-*.json (the clawteam
        CLI and MCP tools write to the new/ subdir). We also check the top-level
        agent dir for backwards compatibility with any legacy senders.
        """
        inboxes_dir = self.team_dir / "inboxes"
        count = 0
        for agent_dir in sorted(inboxes_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name == "agent":
                continue
            agent = agent_dir.name.split("_")[0]
            # Primary: messages in new/ subdir (clawteam CLI, MCP tools)
            new_dir = agent_dir / "new"
            if new_dir.is_dir():
                for msg in sorted(new_dir.glob("msg-*.json")):
                    if not self._is_seen(agent, msg):
                        self._deliver(agent, msg)
                        count += 1
            # Fallback: messages in top-level dir (legacy senders, org redirects)
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
        """Validate pane liveness, kill orphan processes, restart observer.

        Uses `tmux list-panes -s -t soul-team` to get all panes across
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
                    "soul-team",
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

        # Kill orphaned legacy processes (migration period)
        subprocess.run(["pkill", "-f", "soul-sidecar"], capture_output=True)
        subprocess.run(["pkill", "-f", "soul-bridge"], capture_output=True)

        # Verify observer is alive
        if self._observer and not self._observer.is_alive():
            log.warning("Watchdog observer died — restarting")
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

        log.info("Soul Courier running — %d agents", len(self.pane_mgr.panes))

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
