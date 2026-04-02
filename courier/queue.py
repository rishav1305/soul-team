"""Per-agent message queue with in-memory deque and disk persistence."""
import json
import logging
import tempfile
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

log = logging.getLogger("soul-courier.queue")


class MessageQueue:
    def __init__(self, queue_dir: Path):
        self._dir = queue_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._queues: dict[str, deque[Path]] = defaultdict(deque)
        self._lock = threading.Lock()

    def add(self, agent: str, msg_file: Path) -> None:
        with self._lock:
            if msg_file not in self._queues[agent]:
                self._queues[agent].append(msg_file)

    def pop(self, agent: str) -> Optional[Path]:
        with self._lock:
            q = self._queues.get(agent)
            if q:
                return q.popleft()
            return None

    def has_messages(self, agent: str) -> bool:
        with self._lock:
            q = self._queues.get(agent)
            return bool(q)

    def agents_with_messages(self) -> list[str]:
        with self._lock:
            return [a for a, q in list(self._queues.items()) if q]

    def remove(self, agent: str, msg_file: Path) -> None:
        with self._lock:
            q = self._queues.get(agent)
            if q:
                try:
                    q.remove(msg_file)
                except ValueError:
                    pass

    def peek_thread_batch(self, agent: str, min_count: int = 3):
        with self._lock:
            q = self._queues.get(agent)
            if not q or len(q) < min_count:
                return None
            # Snapshot to iterate safely
            queue_snapshot = list(q)
        threads: dict[str, list[Path]] = {}
        for f in queue_snapshot:
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text())
                tid = data.get("thread_id", "")
                if tid and data.get("type") == "group-discussion":
                    threads.setdefault(tid, []).append(f)
            except (json.JSONDecodeError, OSError):
                continue
        for tid, files in threads.items():
            if len(files) >= min_count:
                return (tid, files)
        return None

    def flush(self) -> None:
        with self._lock:
            items = list(self._queues.items())
        for agent, q in items:
            qf = self._dir / f"{agent}.json"
            with self._lock:
                data = [str(p) for p in q]
            tmp = None
            try:
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", dir=self._dir, suffix=".tmp", delete=False
                )
                json.dump(data, tmp)
                tmp.close()
                Path(tmp.name).rename(qf)
            except Exception:
                log.exception("Failed to flush queue for %s", agent)
                if tmp:
                    Path(tmp.name).unlink(missing_ok=True)

    def load(self) -> None:
        for qf in self._dir.glob("*.json"):
            agent = qf.stem
            try:
                data = json.loads(qf.read_text())
                if not isinstance(data, list):
                    raise ValueError("not a list")
                valid = [Path(p) for p in data if Path(p).exists()]
                if valid:
                    with self._lock:
                        self._queues[agent] = deque(valid)
            except (json.JSONDecodeError, ValueError):
                log.warning("Corrupt queue file %s — resetting", qf)
                qf.write_text("[]")
