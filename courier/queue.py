"""Soul Courier — per-agent message queue with disk persistence.

Provides an in-memory deque per agent with periodic flush to disk (JSON).
Supports FIFO ordering, thread-batch detection for overflow batching,
and atomic writes via tempfile + rename.
"""

import json
import logging
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

log = logging.getLogger("soul-courier.queue")


class MessageQueue:
    def __init__(self, queue_dir: Path):
        self._dir = queue_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._queues: dict[str, deque[Path]] = defaultdict(deque)

    def add(self, agent: str, msg_file: Path) -> None:
        self._queues[agent].append(msg_file)

    def pop(self, agent: str) -> Optional[Path]:
        q = self._queues.get(agent)
        if q:
            return q.popleft()
        return None

    def has_messages(self, agent: str) -> bool:
        q = self._queues.get(agent)
        return bool(q)

    def agents_with_messages(self) -> list[str]:
        return [a for a, q in self._queues.items() if q]

    def remove(self, agent: str, msg_file: Path) -> None:
        q = self._queues.get(agent)
        if q:
            try:
                q.remove(msg_file)
            except ValueError:
                pass

    def peek_thread_batch(self, agent: str, min_count: int = 3):
        q = self._queues.get(agent)
        if not q or len(q) < min_count:
            return None
        threads: dict[str, list[Path]] = {}
        for f in q:
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
        for agent, q in self._queues.items():
            qf = self._dir / f"{agent}.json"
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
                    self._queues[agent] = deque(valid)
            except (json.JSONDecodeError, ValueError):
                log.warning("Corrupt queue file %s -- resetting", qf)
                qf.write_text("[]")
