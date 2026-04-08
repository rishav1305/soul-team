"""
STQA Phase B — Unit tests for guardian/guardian-v2.py.

Covers all testable pure functions:
  - run_cmd: subprocess wrapper
  - check_ssh: SSH connectivity check
  - check_http: HTTP health check via curl
  - check_gpu_services: systemd service count check via SSH
  - check_gpu_docker: Docker container count check via SSH
  - write_state, write_alert, clear_alert: state/alert file management

NOTE: The alert threshold (consecutive_failures >= ALERT_AFTER_FAILURES) lives inside
main() as module-level state. Testing it requires extracting a FailureTracker class
(STQA Phase 0 ST-PRE-02 — pending Forge). Tests for alert thresholds are in
TestGuardianV2AlertThreshold below, currently skipped with reason=WAITING_FORGE.

Run: pytest tests/test_guardian_v2.py -v
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Module import ─────────────────────────────────────────────────────────────
# guardian-v2.py has a hyphen — use importlib for import.

_GUARDIAN_V2_PATH = Path(__file__).resolve().parent.parent / "guardian" / "guardian-v2.py"


def _load_guardian_v2():
    """Load guardian-v2 as a fresh module (avoids cross-test state pollution)."""
    spec = importlib.util.spec_from_file_location("guardian_v2", _GUARDIAN_V2_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def gv2():
    """Fresh guardian_v2 module for each test."""
    return _load_guardian_v2()


@pytest.fixture()
def state_dir(tmp_path):
    """Isolated state/alert directory patched into module constants."""
    return tmp_path


# ── TestRunCmd ────────────────────────────────────────────────────────────────


class TestRunCmd:
    """run_cmd(cmd, timeout) — subprocess.run wrapper."""

    def test_success_returns_true_and_stdout(self, gv2):
        with patch.object(gv2.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="hello\n")
            ok, out = gv2.run_cmd("echo hello")
        assert ok is True
        assert out == "hello"

    def test_failure_returns_false(self, gv2):
        with patch.object(gv2.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            ok, out = gv2.run_cmd("false")
        assert ok is False

    def test_timeout_returns_false(self, gv2):
        with patch.object(gv2.subprocess, "run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=10)
            ok, out = gv2.run_cmd("sleep 999", timeout=1)
        assert ok is False
        assert "TimeoutExpired" in out or out  # error string present

    def test_generic_exception_returns_false(self, gv2):
        with patch.object(gv2.subprocess, "run") as mock_run:
            mock_run.side_effect = OSError("some OS error")
            ok, out = gv2.run_cmd("bad-command")
        assert ok is False

    def test_uses_shell_true(self, gv2):
        """run_cmd must pass shell=True (command is a string)."""
        with patch.object(gv2.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            gv2.run_cmd("echo test")
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is True


# ── TestCheckSSH ─────────────────────────────────────────────────────────────


class TestCheckSSH:
    """check_ssh(host, port) — SSH reachability check."""

    def test_pass_when_ssh_returns_ok(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "OK")
            assert gv2.check_ssh("192.168.0.127", port=2222) is True

    def test_fail_when_returncode_nonzero(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            assert gv2.check_ssh("192.168.0.127", port=2222) is False

    def test_fail_when_ok_not_in_output(self, gv2):
        """SSH connected but didn't echo OK — treat as failure."""
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "Connection closed")
            assert gv2.check_ssh("192.168.0.127", port=2222) is False

    def test_fail_when_run_cmd_raises(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "TimeoutExpired")
            assert gv2.check_ssh("10.0.0.1", port=22) is False

    def test_uses_correct_port(self, gv2):
        """SSH command must include the configured port."""
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            gv2.check_ssh("192.168.0.127", port=2222)
        cmd_arg = mock_cmd.call_args[0][0]
        assert "2222" in cmd_arg

    def test_uses_correct_host(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            gv2.check_ssh("192.168.0.99", port=22)
        cmd_arg = mock_cmd.call_args[0][0]
        assert "192.168.0.99" in cmd_arg


# ── TestCheckHTTP ─────────────────────────────────────────────────────────────


class TestCheckHTTP:
    """check_http(host, port) — HTTP health check via curl."""

    def test_pass_on_200(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "200")
            assert gv2.check_http("192.168.0.127", 3002) is True

    def test_fail_on_non_200_status(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "500")
            assert gv2.check_http("192.168.0.127", 3002) is False

    def test_fail_on_404(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "404")
            assert gv2.check_http("192.168.0.127", 3002) is False

    def test_fail_when_curl_exits_nonzero(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            assert gv2.check_http("192.168.0.127", 3002) is False

    def test_uses_correct_host_and_port(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            gv2.check_http("192.168.0.99", 9999)
        cmd_arg = mock_cmd.call_args[0][0]
        assert "192.168.0.99" in cmd_arg
        assert "9999" in cmd_arg


# ── TestCheckGpuServices ──────────────────────────────────────────────────────


class TestCheckGpuServices:
    """check_gpu_services() — count active soul systemd services via SSH."""

    def test_pass_when_count_ge_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "10")
            assert gv2.check_gpu_services() is True

    def test_pass_on_exactly_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "8")
            assert gv2.check_gpu_services() is True

    def test_fail_when_count_lt_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "5")
            assert gv2.check_gpu_services() is False

    def test_fail_on_non_integer_output(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "not-a-number")
            assert gv2.check_gpu_services() is False

    def test_fail_when_ssh_fails(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            assert gv2.check_gpu_services() is False


# ── TestCheckGpuDocker ────────────────────────────────────────────────────────


class TestCheckGpuDocker:
    """check_gpu_docker() — count running Docker containers via SSH."""

    def test_pass_when_count_ge_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "9")
            assert gv2.check_gpu_docker() is True

    def test_pass_on_exactly_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "8")
            assert gv2.check_gpu_docker() is True

    def test_fail_when_count_lt_8(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "3")
            assert gv2.check_gpu_docker() is False

    def test_fail_on_non_integer_output(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (True, "error")
            assert gv2.check_gpu_docker() is False

    def test_fail_when_ssh_fails(self, gv2):
        with patch.object(gv2, "run_cmd") as mock_cmd:
            mock_cmd.return_value = (False, "")
            assert gv2.check_gpu_docker() is False


# ── TestWriteState ────────────────────────────────────────────────────────────


class TestWriteState:
    """write_state(state) — persist check results to STATE_FILE."""

    def test_creates_json_file(self, gv2, state_dir):
        state_file = state_dir / "state.json"
        gv2.STATE_FILE = state_file
        gv2.write_state({"gpu_ssh": True, "consecutive_failures": 0})
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["gpu_ssh"] is True
        assert data["consecutive_failures"] == 0

    def test_overwrites_existing_file(self, gv2, state_dir):
        state_file = state_dir / "state.json"
        gv2.STATE_FILE = state_file
        state_file.write_text(json.dumps({"old": True}))
        gv2.write_state({"new": True})
        data = json.loads(state_file.read_text())
        assert "new" in data
        assert "old" not in data

    def test_writes_valid_json(self, gv2, state_dir):
        state_file = state_dir / "state.json"
        gv2.STATE_FILE = state_file
        gv2.write_state({"version": "2.0.0", "all_ok": False})
        # Must be valid JSON — json.loads raises if not
        parsed = json.loads(state_file.read_text())
        assert parsed["version"] == "2.0.0"


# ── TestWriteAlert ────────────────────────────────────────────────────────────


class TestWriteAlert:
    """write_alert(alert_data) — write alert JSON to ALERT_FILE."""

    def test_creates_alert_file(self, gv2, state_dir):
        alert_file = state_dir / "alert.json"
        log_file = state_dir / "guardian-v2.log"
        gv2.ALERT_FILE = alert_file
        gv2.LOG_FILE = log_file
        gv2.write_alert({"type": "titan_gpu_down", "consecutive_failures": 5})
        assert alert_file.exists()

    def test_alert_contains_correct_fields(self, gv2, state_dir):
        alert_file = state_dir / "alert.json"
        log_file = state_dir / "guardian-v2.log"
        gv2.ALERT_FILE = alert_file
        gv2.LOG_FILE = log_file
        payload = {"type": "titan_gpu_down", "consecutive_failures": 7, "action": "FAILOVER"}
        gv2.write_alert(payload)
        data = json.loads(alert_file.read_text())
        assert data["type"] == "titan_gpu_down"
        assert data["consecutive_failures"] == 7

    def test_overwrites_previous_alert(self, gv2, state_dir):
        alert_file = state_dir / "alert.json"
        log_file = state_dir / "guardian-v2.log"
        gv2.ALERT_FILE = alert_file
        gv2.LOG_FILE = log_file
        gv2.write_alert({"count": 1})
        gv2.write_alert({"count": 2})
        data = json.loads(alert_file.read_text())
        assert data["count"] == 2


# ── TestClearAlert ────────────────────────────────────────────────────────────


class TestClearAlert:
    """clear_alert() — remove ALERT_FILE if it exists."""

    def test_removes_alert_file(self, gv2, state_dir):
        alert_file = state_dir / "alert.json"
        alert_file.write_text(json.dumps({"type": "test"}))
        gv2.ALERT_FILE = alert_file
        gv2.clear_alert()
        assert not alert_file.exists()

    def test_no_error_when_file_missing(self, gv2, state_dir):
        alert_file = state_dir / "nonexistent_alert.json"
        gv2.ALERT_FILE = alert_file
        # Must not raise
        gv2.clear_alert()

    def test_idempotent_double_clear(self, gv2, state_dir):
        alert_file = state_dir / "alert.json"
        alert_file.write_text("{}")
        gv2.ALERT_FILE = alert_file
        gv2.clear_alert()
        gv2.clear_alert()  # Second call must not raise


# ── TestGuardianV2AlertThreshold (pending FailureTracker) ─────────────────────


class TestGuardianV2AlertThreshold:
    """Alert threshold tests — require FailureTracker class (STQA Phase 0 ST-PRE-02).

    These tests are skipped until Forge delivers the FailureTracker extraction.
    The test design follows Fury MC-2 boundary conditions exactly.
    """

    @pytest.mark.skip(reason="Waiting for Forge: FailureTracker class not yet in guardian-v2.py (STQA ST-PRE-02)")
    def test_no_alert_on_4_consecutive_failures(self, gv2, state_dir):
        from guardian_v2 import FailureTracker  # noqa — will exist after Forge delivery
        tracker = FailureTracker(threshold=5)
        for _ in range(4):
            tracker.record_failure("ssh")
        assert tracker.get_count() == 4
        assert not (state_dir / "alert.json").exists()

    @pytest.mark.skip(reason="Waiting for Forge: FailureTracker class not yet in guardian-v2.py (STQA ST-PRE-02)")
    def test_alert_fires_on_5th_consecutive_failure(self, gv2, state_dir):
        from guardian_v2 import FailureTracker  # noqa
        tracker = FailureTracker(threshold=5)
        for _ in range(5):
            triggered = tracker.record_failure("ssh")
        assert triggered is True

    @pytest.mark.skip(reason="Waiting for Forge: FailureTracker class not yet in guardian-v2.py (STQA ST-PRE-02)")
    def test_count_resets_to_zero_after_success(self, gv2):
        from guardian_v2 import FailureTracker  # noqa
        tracker = FailureTracker(threshold=5)
        for _ in range(4):
            tracker.record_failure("ssh")
        tracker.record_success("ssh")
        assert tracker.get_count() == 0

    @pytest.mark.skip(reason="Waiting for Forge: FailureTracker class not yet in guardian-v2.py (STQA ST-PRE-02)")
    def test_alert_not_refired_on_6th_consecutive_failure(self, gv2):
        from guardian_v2 import FailureTracker  # noqa
        tracker = FailureTracker(threshold=5)
        alerts = []
        for _ in range(10):
            triggered = tracker.record_failure("ssh")
            if triggered:
                alerts.append(triggered)
        assert len(alerts) == 1  # fires once, not repeatedly
