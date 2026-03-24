"""Soul Courier — tests for the MessageFormatter module."""

import json
import tempfile
from pathlib import Path
from soul_courier.formatter import MessageFormatter

def _write_msg(td, msg_type="message", **kwargs):
    data = {"type": msg_type, "from": "team-lead", "to": "fury",
            "content": "Hello fury", **kwargs}
    f = Path(td) / "msg-123.json"
    f.write_text(json.dumps(data))
    return f

def test_format_direct():
    with tempfile.TemporaryDirectory() as td:
        f = _write_msg(td)
        text = MessageFormatter.format(f, "fury")
        assert "[INBOX] From: team-lead" in text
        assert "Hello fury" in text
        assert "clawteam inbox send" in text

def test_format_broadcast():
    with tempfile.TemporaryDirectory() as td:
        f = _write_msg(td, msg_type="broadcast")
        text = MessageFormatter.format(f, "fury")
        assert "[BROADCAST]" in text
        assert "team-lead" in text

def test_format_ceo_minimal():
    with tempfile.TemporaryDirectory() as td:
        f = _write_msg(td, **{"from": "fury"})
        text = MessageFormatter.format(f, "team-lead")
        assert "[fury]" in text
        assert "Hello fury" in text
        assert "clawteam" not in text

def test_format_p1_interrupt():
    with tempfile.TemporaryDirectory() as td:
        f = _write_msg(td, key="urgent")
        text = MessageFormatter.format_p1(f, "fury")
        assert "[P1 INTERRUPT" in text
        assert "STEP 1" in text
        assert "STEP 2" in text
        assert "STEP 3" in text

def test_format_discussion():
    with tempfile.TemporaryDirectory() as td:
        f = _write_msg(td, msg_type="group-discussion", thread_id="thread-1")
        text = MessageFormatter.format(f, "fury")
        assert "[DISCUSSION: thread-1]" in text

def test_format_status():
    with tempfile.TemporaryDirectory() as td:
        data = {"type": "status", "from": "sidecar", "action": "crashed",
                "agent": "pepper", "content": "Agent pepper crashed"}
        f = Path(td) / "msg-status.json"
        f.write_text(json.dumps(data))
        text = MessageFormatter.format(f, "team-lead")
        assert "[sidecar]" in text

def test_format_batch():
    with tempfile.TemporaryDirectory() as td:
        files = []
        for i in range(3):
            data = {"type": "group-discussion", "from": f"agent-{i}",
                    "content": f"Message {i}", "thread_id": "t1"}
            f = Path(td) / f"msg-{i}.json"
            f.write_text(json.dumps(data))
            files.append(f)
        text = MessageFormatter.format_batch("t1", files, "fury")
        assert "3 new messages" in text
        assert "agent-0" in text
        assert "agent-2" in text

def test_format_empty_file():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "msg-bad.json"
        f.write_text("NOT JSON")
        text = MessageFormatter.format(f, "fury")
        assert text == ""

def test_format_p1_defaults_from_to_team_lead():
    with tempfile.TemporaryDirectory() as td:
        data = {"type": "message", "from": "agent", "content": "urgent msg"}
        f = Path(td) / "msg-p1.json"
        f.write_text(json.dumps(data))
        text = MessageFormatter.format_p1(f, "fury")
        assert "from team-lead" in text
