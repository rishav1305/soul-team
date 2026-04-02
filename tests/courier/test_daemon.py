"""Tests for CourierDaemon — integration of all courier components."""
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


def test_catchup_processes_messages_in_new_subdir():
    """catchup() must find messages in the new/ subdirectory (standard path)."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        new_dir = base / "inboxes" / "fury_fury" / "new"
        new_dir.mkdir()
        msg = new_dir / "msg-catchup-new-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "from new/"}))
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


def test_first_failure_notifies_ceo():
    """CEO must be notified on the very first delivery failure, not the 5th."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        ceo_inbox = base / "inboxes" / "team-lead_team-lead"
        ceo_inbox.mkdir(parents=True)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)
        # Simulate 1 failure — should notify immediately
        daemon._increment_fail("fury")
        files = list(ceo_inbox.glob("msg-*-courier-fury.json"))
        assert len(files) == 1, "Expected CEO notification after 1st failure"


def test_dlq_after_max_retries():
    """After MAX_RETRIES failures the message is moved to DLQ, not re-queued."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        ceo_inbox = base / "inboxes" / "team-lead_team-lead"
        ceo_inbox.mkdir(parents=True)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)

        msg = base / "inboxes" / "fury_fury" / "msg-dlq-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "dlq test"}))
        daemon.queue.add("fury", msg)

        # Drive fail count to MAX_RETRIES
        from soul_courier.daemon import MAX_RETRIES
        daemon._fail_count["fury"] = MAX_RETRIES - 1
        daemon._increment_fail("fury")  # tips it over the threshold

        # Message must be in DLQ dir, not in the retry queue
        dlq_dir = base / "dlq" / "fury"
        dlq_files = list(dlq_dir.glob("*.json")) if dlq_dir.exists() else []
        assert len(dlq_files) == 1, "Message should be in DLQ after MAX_RETRIES"
        assert not daemon.queue.has_messages("fury"), "Queue should be empty after DLQ"


def test_deliver_sends_receipt_to_sender():
    """After successful delivery, the sender's pane receives a receipt injection."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        # Add loki as a second agent with its own inbox + pane
        loki_inbox = base / "inboxes" / "loki_loki"
        loki_inbox.mkdir(parents=True)
        panes_data = {"fury": "%10", "loki": "%11"}
        (base / "panes.json").write_text(json.dumps(panes_data))

        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=False)
        daemon.pane_mgr.panes = panes_data

        msg = base / "inboxes" / "fury_fury" / "msg-recv-1.json"
        msg.write_text(json.dumps({"type": "message", "from": "loki", "content": "hello fury"}))

        injected_calls = []
        with patch.object(daemon.pane_mgr, "detect_state", return_value="idle"), \
             patch.object(daemon.pane_mgr, "inject", side_effect=lambda agent, text: injected_calls.append((agent, text)) or True), \
             patch.object(daemon.pane_mgr, "verify_injection", return_value=True):
            daemon._deliver("fury", msg)

        # First inject is the message to fury; second should be a receipt to loki
        receipt_calls = [(a, t) for a, t in injected_calls if a == "loki"]
        assert len(receipt_calls) == 1, "Expected one receipt injected to sender (loki)"
        assert "fury" in receipt_calls[0][1], "Receipt should mention recipient (fury)"


def test_p1_interrupt_retries_at_least_five_times():
    """P1 interrupt must try at least 5 times (was 3) before giving up."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)

        call_count = [0]

        def fake_run(cmd, **kwargs):
            if "send-keys" in cmd:
                call_count[0] += 1
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=fake_run), \
             patch.object(daemon.pane_mgr, "detect_state", return_value="busy"), \
             patch.object(daemon.pane_mgr, "invalidate_cache"), \
             patch("soul_courier.daemon.time.sleep"):  # skip real sleeps in tests
            daemon._p1_interrupt("fury")

        # Expect at least 5 C-c send-keys calls (plus empty-Enter flushes)
        assert call_count[0] >= 5, f"Expected ≥5 interrupt attempts, got {call_count[0]}"


def test_status_recorded_on_successful_delivery():
    """StatusStore shows 'delivered' after a successful inject."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=False)

        msg = base / "inboxes" / "fury_fury" / "msg-status-ok.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "hi"}))

        with patch.object(daemon.pane_mgr, "detect_state", return_value="idle"), \
             patch.object(daemon.pane_mgr, "inject", return_value=True), \
             patch.object(daemon.pane_mgr, "verify_injection", return_value=True):
            daemon._deliver("fury", msg)

        entries = daemon.status.get_agent_status("fury")
        assert len(entries) == 1
        assert entries[0]["status"] == "delivered"
        assert entries[0]["file"] == "msg-status-ok.json"


def test_status_recorded_as_failed_on_inject_failure():
    """StatusStore shows 'failed' when inject() returns False."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=False)

        msg = base / "inboxes" / "fury_fury" / "msg-status-fail.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "hi"}))

        with patch.object(daemon.pane_mgr, "detect_state", return_value="idle"), \
             patch.object(daemon.pane_mgr, "inject", return_value=False):
            daemon._deliver("fury", msg)

        entries = daemon.status.get_agent_status("fury")
        assert len(entries) == 1
        assert entries[0]["status"] == "failed"


def test_status_recorded_as_queued_when_agent_busy():
    """StatusStore shows 'queued' when agent pane is busy."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=False)

        msg = base / "inboxes" / "fury_fury" / "msg-status-busy.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "hi"}))

        with patch.object(daemon.pane_mgr, "detect_state", return_value="busy"):
            daemon._deliver("fury", msg)

        entries = daemon.status.get_agent_status("fury")
        assert len(entries) == 1
        assert entries[0]["status"] == "queued"


def test_status_recorded_as_dlq_on_max_retries():
    """StatusStore shows 'dlq' for messages moved to the dead letter queue."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        ceo_inbox = base / "inboxes" / "team-lead_team-lead"
        ceo_inbox.mkdir(parents=True)
        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=True)

        msg = base / "inboxes" / "fury_fury" / "msg-status-dlq.json"
        msg.write_text(json.dumps({"type": "message", "from": "ceo", "content": "dlq"}))
        daemon.queue.add("fury", msg)

        from soul_courier.daemon import MAX_RETRIES
        daemon._fail_count["fury"] = MAX_RETRIES - 1
        daemon._increment_fail("fury", msg_file=msg)

        entries = daemon.status.get_agent_status("fury")
        assert any(e["status"] == "dlq" for e in entries), "Expected at least one dlq entry"


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


def test_deliver_file_only_for_team_lead():
    """team-lead messages use file-only delivery — no pane injection."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        # Add team-lead inbox
        tl_inbox = base / "inboxes" / "team-lead_team-lead"
        tl_inbox.mkdir(parents=True)
        panes_data = {"fury": "%10", "team-lead": "%12"}
        (base / "panes.json").write_text(json.dumps(panes_data))

        daemon = CourierDaemon(team_dir=base, panes_file=base / "panes.json", dry_run=False)

        msg = tl_inbox / "msg-tl-file-1.json"
        msg.write_text(json.dumps({
            "type": "message", "from": "fury", "content": "status update"
        }))

        # Patch inject to track if it's called — it should NOT be
        inject_calls = []
        with patch.object(daemon.pane_mgr, "inject",
                          side_effect=lambda a, t: inject_calls.append((a, t)) or True):
            result = daemon._deliver("team-lead", msg)

        assert result is True
        # inject must NOT have been called for team-lead
        tl_injects = [c for c in inject_calls if c[0] == "team-lead"]
        assert len(tl_injects) == 0, "team-lead should NOT receive pane injection"

        # JSONL delivery log should have the entry
        log_file = base / "delivery-log-team-lead.jsonl"
        assert log_file.exists(), "Delivery log should be created"
        entries = [json.loads(l) for l in log_file.read_text().splitlines()]
        assert len(entries) >= 1
        assert entries[0]["from"] == "fury"
        assert "status update" in entries[0]["content"]

        # Message should be archived
        assert not msg.exists(), "Original message should be archived"
        archive = tl_inbox / "archive"
        assert (archive / msg.name).exists(), "Message should be in archive"


def test_send_receipt_uses_file_for_team_lead():
    """Receipt for team-lead sender goes to file log, not pane injection."""
    with tempfile.TemporaryDirectory() as td:
        base, panes = _setup_dirs(td)
        tl_inbox = base / "inboxes" / "team-lead_team-lead"
        tl_inbox.mkdir(parents=True)

        daemon = CourierDaemon(team_dir=base, panes_file=panes, dry_run=False)

        inject_calls = []
        with patch.object(daemon.pane_mgr, "inject",
                          side_effect=lambda a, t: inject_calls.append((a, t)) or True):
            daemon._send_receipt("team-lead", "fury")

        # No pane injection for team-lead
        assert len(inject_calls) == 0, "team-lead receipts should not use pane injection"

        # Receipt should be in the delivery log
        log_file = base / "delivery-log-team-lead.jsonl"
        assert log_file.exists()
        entries = [json.loads(l) for l in log_file.read_text().splitlines()]
        assert any("fury" in e["content"] for e in entries)
