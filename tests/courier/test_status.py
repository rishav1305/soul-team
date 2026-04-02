"""Tests for StatusStore — per-message delivery status tracking."""
import json
import tempfile
from pathlib import Path
from soul_courier.status import StatusStore


def test_record_delivered():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msg = Path(td) / "msg-test-1.json"
        msg.write_text("{}")
        store.record("fury", msg, "delivered", sender="loki")
        entries = store.get_agent_status("fury")
        assert len(entries) == 1
        assert entries[0]["status"] == "delivered"
        assert entries[0]["sender"] == "loki"
        assert entries[0]["file"] == "msg-test-1.json"


def test_record_persists_to_disk():
    """Status survives across two separate StatusStore instances."""
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msg = Path(td) / "msg-persist.json"
        msg.write_text("{}")
        store.record("fury", msg, "delivered")
        # New instance reads same directory
        store2 = StatusStore(Path(td))
        entries = store2.get_agent_status("fury")
        assert len(entries) == 1
        assert entries[0]["status"] == "delivered"


def test_record_updates_existing():
    """Recording the same file twice updates in-place (no duplicate entries)."""
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msg = Path(td) / "msg-update.json"
        msg.write_text("{}")
        store.record("fury", msg, "queued")
        store.record("fury", msg, "delivered")
        entries = store.get_agent_status("fury")
        assert len(entries) == 1, "Should not create duplicate entries"
        assert entries[0]["status"] == "delivered"


def test_get_all_multiple_agents():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        m1 = Path(td) / "msg-1.json"
        m1.write_text("{}")
        m2 = Path(td) / "msg-2.json"
        m2.write_text("{}")
        store.record("fury", m1, "delivered")
        store.record("loki", m2, "queued")
        all_status = store.get_all()
        assert "fury" in all_status
        assert "loki" in all_status
        assert all_status["fury"][0]["status"] == "delivered"
        assert all_status["loki"][0]["status"] == "queued"


def test_get_summary_counts_by_status():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        for i in range(3):
            m = Path(td) / f"msg-{i}.json"
            m.write_text("{}")
            store.record("fury", m, "delivered")
        m_fail = Path(td) / "msg-fail.json"
        m_fail.write_text("{}")
        store.record("fury", m_fail, "failed")
        summary = store.get_summary("fury")
        assert summary["delivered"] == 3
        assert summary["failed"] == 1
        assert summary.get("queued", 0) == 0


def test_empty_agent_returns_empty_list():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        assert store.get_agent_status("nobody") == []


def test_record_detail_field():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msg = Path(td) / "msg-detail.json"
        msg.write_text("{}")
        store.record("fury", msg, "failed", detail="attempt 3")
        entries = store.get_agent_status("fury")
        assert entries[0]["detail"] == "attempt 3"


def test_corrupt_status_file_returns_empty():
    with tempfile.TemporaryDirectory() as td:
        # Write a corrupt file
        (Path(td) / "fury.json").write_text("NOT JSON {{{")
        store = StatusStore(Path(td))
        assert store.get_agent_status("fury") == []


def test_status_dir_created_automatically():
    with tempfile.TemporaryDirectory() as td:
        nested = Path(td) / "deep" / "status"
        store = StatusStore(nested)
        assert nested.exists()


def test_multiple_messages_same_agent():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msgs = []
        for i in range(5):
            m = Path(td) / f"msg-{i}.json"
            m.write_text("{}")
            msgs.append(m)
            store.record("fury", m, "delivered" if i % 2 == 0 else "failed")
        entries = store.get_agent_status("fury")
        assert len(entries) == 5


def test_record_created_at_set_on_first_record():
    """created_at is set on first record and preserved on updates."""
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        msg = Path(td) / "msg-ts.json"
        msg.write_text("{}")
        store.record("fury", msg, "queued")
        entries = store.get_agent_status("fury")
        created_at = entries[0]["created_at"]

        store.record("fury", msg, "delivered")
        entries2 = store.get_agent_status("fury")
        assert entries2[0]["created_at"] == created_at, "created_at should not change on update"
        assert entries2[0]["updated_at"] >= created_at


def test_get_summary_empty_agent():
    with tempfile.TemporaryDirectory() as td:
        store = StatusStore(Path(td))
        summary = store.get_summary("nobody")
        assert summary == {}
