"""Soul Courier — tmux pane state detection, message injection, and verification.

Manages the lifecycle of tmux pane interactions: detecting whether an agent
pane is idle/busy/crashed/dead, injecting formatted messages via named
buffers, and verifying successful delivery.
"""

import logging
import os
import re
import subprocess
import tempfile
import time
import threading
from typing import Optional

log = logging.getLogger("soul-courier.pane")

CRASHED_RE = re.compile(r'^\$\s*$|^[a-z]+@[a-zA-Z0-9-]+[^>]*\$\s*$', re.M)
IDLE_RE = re.compile(r'[>\u276f]\s*$')


class PaneManager:
    """Manages tmux pane state detection, message injection, and verification."""

    def __init__(self, panes: dict[str, str]):
        self.panes: dict[str, str] = dict(panes)
        self.locks: dict[str, threading.Lock] = {a: threading.Lock() for a in panes}
        self._state_cache: dict[str, tuple[str, float]] = {}
        self._dead_agents: set[str] = set()

    def detect_state(self, agent: str) -> str:
        """Detect pane state: idle, busy, crashed, dead, or crunched."""
        if agent in self._dead_agents:
            return "dead"

        cached = self._state_cache.get(agent)
        if cached and time.monotonic() - cached[1] < 3.0:
            return cached[0]

        pane_id = self.panes.get(agent)
        if not pane_id:
            return "dead"

        content = self._tmux_capture(pane_id, lines=15)
        if content is None:
            return "dead"

        # Check for crashed state (bare shell prompt)
        if CRASHED_RE.search(content):
            state = "crashed"
            self._state_cache[agent] = (state, time.monotonic())
            return state

        # Check for idle/crunched via prompt markers
        non_empty = [l for l in content.splitlines() if l.strip()]
        for line in non_empty:
            if IDLE_RE.search(line):
                state = "crunched" if "Crunched" in content else "idle"
                self._state_cache[agent] = (state, time.monotonic())
                return state

        # Check for crunched without prompt
        if "Crunched" in content:
            state = "crunched"
            self._state_cache[agent] = (state, time.monotonic())
            return state

        # Ambiguous -- take two snapshots to detect activity
        snapshot1 = content
        time.sleep(1.5)
        snapshot2 = self._tmux_capture(pane_id, lines=15)
        if snapshot2 and any(IDLE_RE.search(l) for l in snapshot2.splitlines() if l.strip()):
            state = "crunched" if "Crunched" in snapshot2 else "idle"
        elif snapshot1 == snapshot2:
            state = "idle"
        else:
            state = "busy"

        self._state_cache[agent] = (state, time.monotonic())
        return state

    def inject(self, agent: str, text: str) -> bool:
        """Inject a message into an agent's tmux pane via named buffer."""
        pane_id = self.panes.get(agent)
        if not pane_id:
            return False

        buf_name = f"courier-{agent}"
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w") as f:
                f.write(text)

            subprocess.run(
                ["tmux", "load-buffer", "-b", buf_name, tmp_path],
                check=True, capture_output=True, timeout=5
            )
            subprocess.run(
                ["tmux", "paste-buffer", "-b", buf_name, "-t", pane_id, "-d"],
                check=True, capture_output=True, timeout=5
            )
            time.sleep(0.3)
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                check=True, capture_output=True, timeout=5
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            log.warning("Inject failed for %s: %s", agent, e)
            return False
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def verify_injection(self, agent: str, fragment: str, wait: float = 2.0) -> bool:
        """Verify that a message fragment appears in the pane after injection."""
        time.sleep(wait)
        pane_id = self.panes.get(agent)
        if not pane_id:
            return False
        content = self._tmux_capture(pane_id, lines=30)
        return content is not None and fragment in content

    def update_panes(self, panes: dict[str, str]) -> None:
        """Update the pane map, preserving existing locks for known agents."""
        old_locks = dict(self.locks)
        self.panes = dict(panes)
        self.locks = {}
        for a in panes:
            self.locks[a] = old_locks.get(a) or threading.Lock()
        self._state_cache.clear()
        self._dead_agents.clear()

    def mark_dead(self, agent: str) -> None:
        """Mark an agent as dead -- detect_state will return 'dead' immediately."""
        self._dead_agents.add(agent)
        self.panes.pop(agent, None)

    def invalidate_cache(self, agent: str) -> None:
        """Force next detect_state call to re-query tmux."""
        self._state_cache.pop(agent, None)

    def _tmux_capture(self, pane_id: str, lines: int = 15) -> Optional[str]:
        """Capture the last N lines from a tmux pane."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
