"""Soul Courier — tests for the CourierDaemon integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from soul_courier.daemon import CourierDaemon


def _setup_dirs(td):
    """Create minimal directory structure for daemon."""
    base = Path(td)
    inboxes = base / "inboxes" / "fury_fury"
    inboxes.mkdir(parents=True)
    (inboxes / "archive").mkdir()
    queue = base / "queue"
    queue.mkdir()
    sidecar = base / "sidecar"
    sidecar.mkdir()
    panes = base / "panes.json"
    panes.write_text(json.dumps({"fury": "%10"}))
    return base, panes


def test_load_panes():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        assert daemon.pane_mgr.panes == {"fury": "%10"}


def test_is_seen_and_mark_seen():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        msg = base / "inboxes" / "fury_fury" / "msg-test-123.json"
        msg.write_text('{"content":"test"}')
        assert not daemon._is_seen("fury", msg)
        daemon._mark_seen(msg)
        assert daemon._is_seen("fury", msg)


def test_is_seen_scoped_to_agent():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        # Add hawkeye inbox
        hawk_inbox = base / "inboxes" / "hawkeye_hawkeye"
        hawk_inbox.mkdir(parents=True)
        panes_data = {"fury": "%10", "hawkeye": "%11"}
        (base / "panes.json").write_text(json.dumps(panes_data))
        daemon = CourierDaemon(team_dir=base, panes_file=base / "panes.json", dry_run=True)
        msg = base / "inboxes" / "fury_fury" / "msg-scope-1.json"
        msg.write_text('{"content":"scoped"}')
        daemon._mark_seen(msg)
        assert daemon._is_seen("fury", msg)
        assert not daemon._is_seen("hawkeye", msg)


def test_catchup_processes_unseen():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        inbox = base / "inboxes" / "fury_fury"
        msg = inbox / "msg-catchup-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "test"}))
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        with patch.object(daemon, "_deliver") as mock_deliver:
            daemon.catchup()
            mock_deliver.assert_called_once_with("fury", msg)


def test_catchup_skips_seen():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        inbox = base / "inboxes" / "fury_fury"
        msg = inbox / "msg-seen-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "old"}))
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        daemon._mark_seen(msg)
        with patch.object(daemon, "_deliver") as mock_deliver:
            daemon.catchup()
            mock_deliver.assert_not_called()


def test_agent_from_path():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        msg = base / "inboxes" / "fury_fury" / "msg-123.json"
        assert daemon._agent_from_path(msg) == "fury"
        msg2 = base / "inboxes" / "team-lead_team-lead" / "msg-456.json"
        assert daemon._agent_from_path(msg2) == "team-lead"


def test_deliver_dry_run_queues():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        msg = base / "inboxes" / "fury_fury" / "msg-dry-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "hello"}))
        with patch.object(daemon.pane_mgr, "detect_state", return_value="idle"):
            result = daemon._deliver("fury", msg)
            # dry_run skips inject, so it falls through to queue
            assert not result
            assert daemon.queue.has_messages("fury")


def test_notify_ceo_creates_file():
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        ceo_inbox = base / "inboxes" / "team-lead_team-lead"
        ceo_inbox.mkdir(parents=True)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        daemon._notify_ceo("fury", "crashed")
        files = list(ceo_inbox.glob("msg-*-courier-fury.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["action"] == "crashed"
        assert data["agent"] == "fury"
