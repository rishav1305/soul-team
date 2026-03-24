"""Soul Courier — watchdog event handler for agent inbox directories.

Monitors the inboxes/ directory tree for new message files arriving via
atomic rename (the standard delivery mechanism from the clawteam CLI).
Only msg-*.json files in properly-named inbox dirs are dispatched;
archive/, temp files, non-JSON, and directory events are ignored.
"""

import logging
import re
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler, FileMovedEvent

log = logging.getLogger("soul-courier.watcher")

# Matches: /inboxes/{agent}_{agent}/msg-*.json
# Backreference \1 ensures the folder name pattern {name}_{name} is consistent.
INBOX_RE = re.compile(r"/inboxes/([a-z][\w-]*)_\1/(msg-[^/]+\.json)$")


class InboxWatcher(FileSystemEventHandler):
    """Detects new messages arriving in agent inbox directories.

    Messages arrive as atomic renames (moved_to events) from the clawteam CLI.
    Only msg-*.json files in top-level inbox dirs are dispatched; archive/,
    temp files, non-JSON, and directory events are all ignored.
    """

    def __init__(self, callback: Callable[[str, Path], None]):
        super().__init__()
        self._callback = callback

    def on_moved(self, event: FileMovedEvent) -> None:
        """Handle file move events -- the primary delivery mechanism."""
        if getattr(event, "_is_directory", False) or getattr(
            event, "is_directory", False
        ):
            return
        dest = event.dest_path
        agent = self._parse_agent(dest)
        if agent:
            log.info("New message for %s: %s", agent, Path(dest).name)
            self._callback(agent, Path(dest))

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
