"""Watchdog event handler for agent inbox directories."""
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileMovedEvent,
)

log = logging.getLogger("soul-courier.watcher")

# Matches messages in both locations:
#   /inboxes/{agent}_{agent}/msg-*.json          (legacy, top-level)
#   /inboxes/{agent}_{agent}/new/msg-*.json      (standard, clawteam CLI + MCP)
# Backreference \1 ensures the folder name pattern {name}_{name} is consistent.
INBOX_RE = re.compile(r"/inboxes/([a-z][\w-]*)_\1/(?:new/)?(msg-[^/]+\.json)$")


class InboxWatcher(FileSystemEventHandler):
    """Detects new messages arriving in agent inbox directories.

    Messages arrive via two mechanisms:
    1. Atomic renames (on_moved) — from clawteam CLI's tmp→final rename pattern
    2. Direct file creation (on_created) — from MCP soul_send_message and
       any tool that writes msg-*.json files directly to the inbox

    Only msg-*.json files in inbox dirs (or new/ subdirs) are dispatched;
    archive/, temp files, non-JSON, and directory events are all ignored.
    """

    def __init__(self, callback: Callable[[str, Path], None]):
        super().__init__()
        self._callback = callback

    def on_moved(self, event: FileMovedEvent) -> None:
        """Handle file move events — atomic rename delivery."""
        if getattr(event, "_is_directory", False) or getattr(
            event, "is_directory", False
        ):
            return
        dest = event.dest_path
        self._dispatch(dest)

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation events — direct write delivery (MCP, scripts)."""
        if getattr(event, "_is_directory", False) or getattr(
            event, "is_directory", False
        ):
            return
        self._dispatch(event.src_path)

    def _dispatch(self, path: str) -> None:
        """Common dispatch logic for both moved and created events."""
        agent = self._parse_agent(path)
        if agent:
            log.info("New message for %s: %s", agent, Path(path).name)
            self._callback(agent, Path(path))

    def _parse_agent(self, path: str) -> Optional[str]:
        """Extract agent name from an inbox path, or None if not a valid message."""
        p = Path(path)
        if p.suffix != ".json":
            return None
        if p.name.startswith(".tmp"):
            return None
        if "archive" in p.parts:
            return None
        m = INBOX_RE.search(path)
        if m:
            return m.group(1)
        return None
