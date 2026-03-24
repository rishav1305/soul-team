"""Soul Courier — message delivery daemon for soul-team multi-agent systems.

Watches agent inbox directories for new messages and delivers them to the
appropriate tmux panes with formatting, queuing, and retry logic.

Key classes:
    CourierDaemon   — Main daemon orchestrating delivery, health checks, and queues.
    MessageFormatter — Formats messages for tmux pane injection.
    PaneManager     — Manages tmux pane state detection and message injection.
    MessageQueue    — Per-agent message queue with disk persistence.
    InboxWatcher    — Watchdog filesystem handler for inbox directories.
"""

from soul_courier.daemon import CourierDaemon
from soul_courier.formatter import MessageFormatter
from soul_courier.pane import PaneManager
from soul_courier.queue import MessageQueue
from soul_courier.watcher import InboxWatcher

__all__ = [
    "CourierDaemon",
    "MessageFormatter",
    "PaneManager",
    "MessageQueue",
    "InboxWatcher",
]
