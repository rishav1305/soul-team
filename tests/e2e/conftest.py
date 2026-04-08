"""
STQA2 Phase 3 — E2E test fixtures for soul-team courier messaging.

Fixtures:
  - tmp_team_dir: isolated temp directory with proper inbox structure
  - courier_instance: live CourierDaemon watching tmp_team_dir
  - message_helpers: utility functions for writing/reading messages

Architecture note: The MCP server is stdio-only (no HTTP). E2E tests
exercise the courier daemon's filesystem-based delivery chain directly:
  write msg to inbox → courier picks up → archives + marks seen
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure repo root is on sys.path for soul_courier imports.
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


@pytest.fixture(scope="session")
def tmp_team_dir(tmp_path_factory):
    """Create an isolated team directory with proper inbox structure."""
    team_dir = tmp_path_factory.mktemp("soul-team-e2e")

    # Create inbox dirs for test agents.
    for agent in ("agent-a", "agent-b", "agent-c", "team-lead"):
        inbox = team_dir / "inboxes" / f"{agent}_{agent}" / "new"
        inbox.mkdir(parents=True)

    # Create queue dir.
    (team_dir / "queue").mkdir()

    # Create sidecar dir for seen tracking.
    (team_dir / "sidecar").mkdir()

    # Create status dir.
    (team_dir / "status").mkdir()

    # Create empty panes.json — no tmux panes in test mode.
    (team_dir / "panes.json").write_text(json.dumps({}))

    return team_dir


@pytest.fixture(scope="session")
def courier_instance(tmp_team_dir):
    """Start an isolated CourierDaemon watching tmp_team_dir.

    Uses dry_run=False but with empty panes.json — agents without panes
    get file-only delivery (archive + mark seen) or queue on failure.
    The courier still processes messages and archives them.
    """
    from soul_courier.daemon import CourierDaemon

    # Override FILE_ONLY_AGENTS to include our test agents.
    import soul_courier.daemon as daemon_mod
    original_file_only = daemon_mod.FILE_ONLY_AGENTS
    daemon_mod.FILE_ONLY_AGENTS = {"agent-a", "agent-b", "agent-c", "team-lead"}

    # Override NATIVE_INBOX_DIR to avoid touching real inboxes.
    original_native = daemon_mod.NATIVE_INBOX_DIR
    daemon_mod.NATIVE_INBOX_DIR = tmp_team_dir / "native-inboxes"
    daemon_mod.NATIVE_INBOX_DIR.mkdir(parents=True, exist_ok=True)

    daemon = CourierDaemon(
        team_dir=tmp_team_dir,
        panes_file=tmp_team_dir / "panes.json",
    )

    # Start daemon in background thread.
    t = threading.Thread(target=daemon.start, daemon=True)
    t.start()

    # Wait for daemon to be ready (must be running + observer alive).
    for _ in range(100):
        if daemon._running and daemon._observer and daemon._observer.is_alive():
            break
        time.sleep(0.1)
    # Extra settle time for watchdog inotify to register watches.
    time.sleep(0.5)

    yield {
        "daemon": daemon,
        "team_dir": tmp_team_dir,
        "thread": t,
    }

    # Cleanup.
    daemon.stop()
    daemon_mod.FILE_ONLY_AGENTS = original_file_only
    daemon_mod.NATIVE_INBOX_DIR = original_native


class MessageHelpers:
    """Helper methods for writing and checking messages."""

    def __init__(self, team_dir: Path):
        self.team_dir = team_dir
        self._counter = 0

    def send_message(self, from_agent: str, to_agent: str, content: str,
                     message_id: str = None, extra: dict = None) -> Path:
        """Write a message JSON file to the recipient's inbox.

        Returns the path to the written message file.
        """
        self._counter += 1
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        msg_id = message_id or f"msg-{int(time.time())}-{self._counter}"

        data = {
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "timestamp": ts,
            "type": "message",
        }
        if extra:
            data.update(extra)

        inbox_dir = self.team_dir / "inboxes" / f"{to_agent}_{to_agent}" / "new"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        msg_file = inbox_dir / f"{msg_id}.json"
        msg_file.write_text(json.dumps(data))
        return msg_file

    def count_archived(self, agent: str) -> int:
        """Count current archived messages for an agent."""
        base = self.team_dir / "inboxes" / f"{agent}_{agent}"
        count = 0
        for archive_dir in [base / "archive", base / "new" / "archive"]:
            if archive_dir.exists():
                count += len(list(archive_dir.glob("*.json")))
        return count

    def wait_for_archive(self, agent: str, timeout: float = 5.0,
                         min_count: int = 1) -> list[Path]:
        """Wait for at least min_count messages in agent's archive.

        Checks both inbox/archive/ and inbox/new/archive/ paths since
        the courier archives relative to msg_file.parent.
        """
        base = self.team_dir / "inboxes" / f"{agent}_{agent}"
        archive_dirs = [base / "archive", base / "new" / "archive"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            all_files = []
            for archive_dir in archive_dirs:
                if archive_dir.exists():
                    all_files.extend(archive_dir.glob("*.json"))
            if len(all_files) >= min_count:
                return all_files
            time.sleep(0.05)
        all_files = []
        for archive_dir in archive_dirs:
            if archive_dir.exists():
                all_files.extend(archive_dir.glob("*.json"))
        return all_files

    def get_archived_messages(self, agent: str) -> list[dict]:
        """Read all archived messages for an agent."""
        base = self.team_dir / "inboxes" / f"{agent}_{agent}"
        messages = []
        for archive_dir in [base / "archive", base / "new" / "archive"]:
            if not archive_dir.exists():
                continue
            for f in sorted(archive_dir.glob("*.json")):
                try:
                    messages.append(json.loads(f.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass
        return messages

    def get_delivery_log(self, agent: str) -> list[dict]:
        """Read the JSONL delivery log for an agent."""
        log_file = self.team_dir / f"delivery-log-{agent}.jsonl"
        if not log_file.exists():
            return []
        entries = []
        for line in log_file.read_text().splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries

    def count_inbox_files(self, agent: str) -> int:
        """Count unprocessed messages in agent's inbox."""
        new_dir = self.team_dir / "inboxes" / f"{agent}_{agent}" / "new"
        if not new_dir.exists():
            return 0
        return len(list(new_dir.glob("*.json")))


@pytest.fixture(scope="session")
def message_helpers(tmp_team_dir):
    """Provide message writing/reading helpers."""
    return MessageHelpers(tmp_team_dir)
