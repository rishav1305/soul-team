"""Soul Courier — tests for the InboxWatcher module."""

from pathlib import Path
from unittest.mock import MagicMock

from watchdog.events import FileMovedEvent

from soul_courier.watcher import InboxWatcher


def test_parse_agent_from_path():
    w = InboxWatcher(callback=MagicMock())
    assert w._parse_agent("/inboxes/fury_fury/msg-123.json") == "fury"
    assert w._parse_agent("/inboxes/team-lead_team-lead/msg-456.json") == "team-lead"
    assert w._parse_agent("/inboxes/fury_fury/archive/msg-123.json") is None
    assert w._parse_agent("/inboxes/fury_fury/.tmp-123.json") is None
    assert w._parse_agent("/inboxes/fury_fury/not-a-msg.txt") is None


def test_on_moved_dispatches():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/.tmp-123.json",
        dest_path="/home/user/.clawteam/teams/my-team/inboxes/fury_fury/msg-123.json",
    )
    w.on_moved(event)
    cb.assert_called_once()
    args = cb.call_args
    assert args[0][0] == "fury"
    assert "msg-123.json" in str(args[0][1])


def test_on_moved_ignores_archive():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/.tmp-123.json",
        dest_path="/inboxes/fury_fury/archive/msg-123.json",
    )
    w.on_moved(event)
    cb.assert_not_called()


def test_on_moved_ignores_non_json():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/file.txt",
        dest_path="/inboxes/fury_fury/file.txt",
    )
    w.on_moved(event)
    cb.assert_not_called()


def test_on_moved_ignores_directory():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/dir",
        dest_path="/inboxes/fury_fury/somedir",
    )
    event._is_directory = True
    w.on_moved(event)
    cb.assert_not_called()
