"""Tests for InboxWatcher — watchdog handler for agent inbox directories."""
from pathlib import Path
from unittest.mock import MagicMock

from watchdog.events import FileCreatedEvent, FileMovedEvent

from soul_courier.watcher import InboxWatcher


def test_parse_agent_from_path():
    w = InboxWatcher(callback=MagicMock())
    # Top-level (legacy)
    assert w._parse_agent("/inboxes/fury_fury/msg-123.json") == "fury"
    assert w._parse_agent("/inboxes/team-lead_team-lead/msg-456.json") == "team-lead"
    # new/ subdir (standard clawteam + MCP path)
    assert w._parse_agent("/inboxes/fury_fury/new/msg-789.json") == "fury"
    assert w._parse_agent("/inboxes/team-lead_team-lead/new/msg-abc.json") == "team-lead"
    # Rejected paths
    assert w._parse_agent("/inboxes/fury_fury/archive/msg-123.json") is None
    assert w._parse_agent("/inboxes/fury_fury/.tmp-123.json") is None
    assert w._parse_agent("/inboxes/fury_fury/not-a-msg.txt") is None
    assert w._parse_agent("/inboxes/fury_fury/new/.tmp-123.json") is None


def test_on_moved_dispatches():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/.tmp-123.json",
        dest_path="/home/rishav/.clawteam/teams/soul-team/inboxes/fury_fury/msg-123.json",
    )
    w.on_moved(event)
    cb.assert_called_once()
    args = cb.call_args
    assert args[0][0] == "fury"
    assert "msg-123.json" in str(args[0][1])


def test_on_moved_dispatches_new_subdir():
    """on_moved detects messages in the new/ subdir."""
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileMovedEvent(
        src_path="/tmp/.tmp-456.json",
        dest_path="/home/rishav/.clawteam/teams/soul-team/inboxes/fury_fury/new/msg-456.json",
    )
    w.on_moved(event)
    cb.assert_called_once()
    assert cb.call_args[0][0] == "fury"


def test_on_created_dispatches():
    """on_created detects directly written messages (MCP, scripts)."""
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileCreatedEvent(
        src_path="/home/rishav/.clawteam/teams/soul-team/inboxes/fury_fury/new/msg-mcp-1.json",
    )
    w.on_created(event)
    cb.assert_called_once()
    args = cb.call_args
    assert args[0][0] == "fury"
    assert "msg-mcp-1.json" in str(args[0][1])


def test_on_created_ignores_archive():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileCreatedEvent(
        src_path="/inboxes/fury_fury/archive/msg-123.json",
    )
    w.on_created(event)
    cb.assert_not_called()


def test_on_created_ignores_tmp_files():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileCreatedEvent(
        src_path="/inboxes/fury_fury/new/.tmp-123.json",
    )
    w.on_created(event)
    cb.assert_not_called()


def test_on_created_ignores_directory():
    cb = MagicMock()
    w = InboxWatcher(callback=cb)
    event = FileCreatedEvent(
        src_path="/inboxes/fury_fury/new/somedir",
    )
    event._is_directory = True
    w.on_created(event)
    cb.assert_not_called()


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
