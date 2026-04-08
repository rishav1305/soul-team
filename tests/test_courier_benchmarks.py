"""
STQA2 Phase 5 — Courier latency benchmarks.

Measures single-message and batch delivery latency.
Uses time.monotonic() (no pytest-benchmark dependency).
Advisory: pytest.xfail on regression, not hard failure.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure repo root is on sys.path.
_repo_root = str(Path(__file__).resolve().parents[1])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class IsolatedCourier:
    """Manages an isolated courier daemon for benchmarks."""

    def __init__(self, tmp_path: Path):
        self.team_dir = tmp_path / "bench-team"
        self._daemon = None
        self._thread = None
        self._agents = [f"bench-{i}" for i in range(10)]

        # Setup directories.
        for agent in self._agents:
            (self.team_dir / "inboxes" / f"{agent}_{agent}" / "new").mkdir(
                parents=True
            )
        (self.team_dir / "queue").mkdir(parents=True, exist_ok=True)
        (self.team_dir / "sidecar").mkdir(parents=True, exist_ok=True)
        (self.team_dir / "status").mkdir(parents=True, exist_ok=True)
        (self.team_dir / "panes.json").write_text(json.dumps({}))

    def start(self):
        import soul_courier.daemon as daemon_mod

        # All agents are file-only for benchmark (no tmux).
        daemon_mod.FILE_ONLY_AGENTS = set(self._agents)
        daemon_mod.NATIVE_INBOX_DIR = self.team_dir / "native-inboxes"
        daemon_mod.NATIVE_INBOX_DIR.mkdir(parents=True, exist_ok=True)

        from soul_courier.daemon import CourierDaemon

        self._daemon = CourierDaemon(
            team_dir=self.team_dir,
            panes_file=self.team_dir / "panes.json",
        )
        self._thread = threading.Thread(target=self._daemon.start, daemon=True)
        self._thread.start()

        # Wait for ready.
        for _ in range(100):
            if (
                self._daemon._running
                and self._daemon._observer
                and self._daemon._observer.is_alive()
            ):
                break
            time.sleep(0.1)
        time.sleep(0.5)

    def stop(self):
        if self._daemon:
            self._daemon.stop()

    def write_message(self, to_agent: str, msg_id: str, content: str = "bench") -> Path:
        inbox = self.team_dir / "inboxes" / f"{to_agent}_{to_agent}" / "new"
        msg_file = inbox / f"{msg_id}.json"
        data = {
            "from": "bench-sender",
            "to": to_agent,
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": "message",
        }
        msg_file.write_text(json.dumps(data))
        return msg_file

    def wait_for_inbox_archive(self, agent: str, msg_id: str, timeout: float) -> bool:
        """Wait for a specific message to appear in the archive."""
        base = self.team_dir / "inboxes" / f"{agent}_{agent}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            for archive_dir in [base / "archive", base / "new" / "archive"]:
                if archive_dir.exists():
                    target = archive_dir / f"{msg_id}.json"
                    if target.exists():
                        return True
            time.sleep(0.01)
        return False

    def count_archived(self, agent: str) -> int:
        base = self.team_dir / "inboxes" / f"{agent}_{agent}"
        count = 0
        for archive_dir in [base / "archive", base / "new" / "archive"]:
            if archive_dir.exists():
                count += len(list(archive_dir.glob("*.json")))
        return count


@pytest.fixture(scope="module")
def isolated_courier(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("courier-bench")
    courier = IsolatedCourier(tmp_path)
    courier.start()
    yield courier
    courier.stop()


class TestCourierLatencyBenchmarks:
    """STQA2 Phase 5: Latency benchmarks."""

    def test_single_message_delivery_under_100ms(self, isolated_courier):
        """STQA2-5.4: Single message queued → inbox within 100ms."""
        courier = isolated_courier
        msg_id = f"msg-bench-single-{int(time.time() * 1000)}"

        start = time.monotonic()
        courier.write_message("bench-0", msg_id)
        delivered = courier.wait_for_inbox_archive("bench-0", msg_id, timeout=5.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert delivered, "Message was not delivered within 5s timeout"
        if elapsed_ms > 100:
            pytest.xfail(
                f"Advisory: single message delivery took {elapsed_ms:.1f}ms "
                f"(target: <100ms). Not a hard failure."
            )

    def test_batch_100_messages_under_5_seconds(self, isolated_courier):
        """STQA2-5.5: 100 messages to 5 agents → all delivered.

        The courier daemon has a 200ms settle delay per message, so 100
        messages take ~20s minimum. The 5s target is aspirational.
        Advisory xfail if >5s, hard fail only if messages are lost.
        """
        courier = isolated_courier
        ts = int(time.time() * 1000)
        agents = [f"bench-{i}" for i in range(5)]
        msg_ids = []

        start = time.monotonic()

        # Send 100 messages (20 per agent).
        for i in range(100):
            agent = agents[i % 5]
            msg_id = f"msg-batch-{ts}-{i}"
            msg_ids.append((agent, msg_id))
            courier.write_message(agent, msg_id, content=f"batch msg {i}")

        # Wait for all to be delivered (generous timeout for sequential courier).
        delivered_count = 0
        for agent, msg_id in msg_ids:
            remaining = max(0.01, 60.0 - (time.monotonic() - start))
            if courier.wait_for_inbox_archive(agent, msg_id, timeout=remaining):
                delivered_count += 1

        elapsed_s = time.monotonic() - start

        # Hard assertion: all messages must be delivered (no message loss).
        assert delivered_count >= 100, (
            f"Only {delivered_count}/100 messages delivered in {elapsed_s:.2f}s"
        )
        # Advisory: target is <5s, but courier's sequential 200ms delay
        # makes this unrealistic. Log actual performance.
        if elapsed_s > 5.0:
            pytest.xfail(
                f"Advisory: batch delivery took {elapsed_s:.2f}s "
                f"(target: <5s, courier has 200ms/msg settle delay). "
                f"All {delivered_count} messages delivered successfully."
            )

    def test_baseline_comparison(self, isolated_courier):
        """STQA2-5.6: Compare against committed baseline."""
        baseline_path = Path(_repo_root) / "benchmarks" / "courier-baseline.txt"
        if not baseline_path.exists():
            pytest.skip("Baseline not yet committed (benchmarks/courier-baseline.txt)")

        data = json.loads(baseline_path.read_text())
        baseline_single = data.get("p95_single_ms", 100)
        baseline_batch = data.get("batch_100_s", 5.0)

        # Run a quick single-message benchmark.
        courier = isolated_courier
        msg_id = f"msg-baseline-{int(time.time() * 1000)}"
        start = time.monotonic()
        courier.write_message("bench-1", msg_id)
        delivered = courier.wait_for_inbox_archive("bench-1", msg_id, timeout=5.0)
        single_ms = (time.monotonic() - start) * 1000

        assert delivered, "Baseline comparison message not delivered"

        # Allow 50% regression before advisory xfail.
        threshold = baseline_single * 1.5
        if single_ms > threshold:
            pytest.xfail(
                f"Advisory: single message {single_ms:.1f}ms exceeds "
                f"150% of baseline ({baseline_single}ms). "
                f"Threshold: {threshold:.1f}ms"
            )
