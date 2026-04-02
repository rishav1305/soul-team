import json
import tempfile
from pathlib import Path
from soul_courier.queue import MessageQueue

def test_add_and_pop():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        msg = Path(td) / "msg-123.json"
        msg.write_text('{"content":"hello"}')
        q.add("fury", msg)
        result = q.pop("fury")
        assert result == msg
        assert q.pop("fury") is None

def test_pop_empty_returns_none():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        assert q.pop("fury") is None

def test_fifo_ordering():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        msgs = []
        for i in range(3):
            m = Path(td) / f"msg-{i}.json"
            m.write_text(f'{{"i":{i}}}')
            msgs.append(m)
            q.add("fury", m)
        for i in range(3):
            assert q.pop("fury") == msgs[i]

def test_flush_and_reload():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        msg = Path(td) / "msg-456.json"
        msg.write_text('{"content":"persist"}')
        q.add("fury", msg)
        q.flush()
        qf = Path(td) / "fury.json"
        assert qf.exists()
        data = json.loads(qf.read_text())
        assert len(data) == 1
        q2 = MessageQueue(Path(td))
        q2.load()
        result = q2.pop("fury")
        assert result == msg

def test_flush_skips_missing_files():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        ghost = Path(td) / "msg-ghost.json"
        q.add("fury", ghost)
        q.flush()
        q2 = MessageQueue(Path(td))
        q2.load()
        assert q2.pop("fury") is None

def test_has_messages():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        assert not q.has_messages("fury")
        msg = Path(td) / "msg-789.json"
        msg.write_text('{}')
        q.add("fury", msg)
        assert q.has_messages("fury")

def test_agents_with_messages():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        m1 = Path(td) / "msg-1.json"; m1.write_text('{}')
        m2 = Path(td) / "msg-2.json"; m2.write_text('{}')
        q.add("fury", m1)
        q.add("hawkeye", m2)
        agents = q.agents_with_messages()
        assert set(agents) == {"fury", "hawkeye"}

def test_corrupt_queue_file_resets():
    with tempfile.TemporaryDirectory() as td:
        qf = Path(td) / "fury.json"
        qf.write_text("NOT VALID JSON {{{{")
        q = MessageQueue(Path(td))
        q.load()
        assert q.pop("fury") is None

def test_remove():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        m1 = Path(td) / "msg-1.json"; m1.write_text('{}')
        m2 = Path(td) / "msg-2.json"; m2.write_text('{}')
        q.add("fury", m1)
        q.add("fury", m2)
        q.remove("fury", m1)
        assert q.pop("fury") == m2
        assert q.pop("fury") is None

def test_peek_thread_batch_none():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        assert q.peek_thread_batch("fury") is None

def test_add_deduplicates_same_file():
    """Adding the same Path twice must not enqueue it twice."""
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        msg = Path(td) / "msg-dup.json"
        msg.write_text('{"content":"dup"}')
        q.add("fury", msg)
        q.add("fury", msg)  # second add of same file
        q.pop("fury")        # removes the only entry
        assert q.pop("fury") is None  # queue is now empty


def test_peek_thread_batch_found():
    with tempfile.TemporaryDirectory() as td:
        q = MessageQueue(Path(td))
        for i in range(3):
            m = Path(td) / f"msg-{i}.json"
            m.write_text(json.dumps({"type": "group-discussion", "thread_id": "t1", "content": f"msg {i}"}))
            q.add("fury", m)
        result = q.peek_thread_batch("fury", min_count=3)
        assert result is not None
        tid, files = result
        assert tid == "t1"
        assert len(files) == 3
