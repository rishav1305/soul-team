"""
STQA2 Phase 2 — Unit tests for ops.health module.

Tests all 4 health check functions with mocked subprocess/shutil/psutil.
All tests verify that functions NEVER raise — they return safe defaults on any error.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ops.health import (
    check_disk_usage,
    check_docker_container,
    check_memory_pressure,
    check_service_active,
)


class TestCheckServiceActive:
    """STQA2-2.1: 6 tests for check_service_active (5 spec + 1 edge case)."""

    @patch("ops.health.subprocess.run")
    def test_active_returns_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert check_service_active("sshd") is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["systemctl", "is-active", "--quiet", "sshd"]

    @patch("ops.health.subprocess.run")
    def test_inactive_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=3)
        assert check_service_active("stopped-service") is False

    @patch("ops.health.subprocess.run")
    def test_not_found_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=4)
        assert check_service_active("nonexistent") is False

    @patch("ops.health.subprocess.run")
    def test_file_not_found_returns_false(self, mock_run):
        mock_run.side_effect = FileNotFoundError("systemctl not found")
        assert check_service_active("sshd") is False

    @patch("ops.health.subprocess.run")
    def test_timeout_returns_false(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl", timeout=10)
        assert check_service_active("sshd") is False

    @patch("ops.health.subprocess.run")
    def test_generic_exception_returns_false(self, mock_run):
        """Any unexpected exception must not propagate — Guardian v2 stability contract."""
        mock_run.side_effect = OSError("unexpected os error")
        assert check_service_active("sshd") is False


class TestCheckDockerContainer:
    """STQA2-2.2: 6 tests for check_docker_container (4 spec + 2 edge cases)."""

    @patch("ops.health.subprocess.run")
    def test_running_returns_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="running\n")
        assert check_docker_container("gitea") is True

    @patch("ops.health.subprocess.run")
    def test_exited_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="exited\n")
        assert check_docker_container("gitea") is False

    @patch("ops.health.subprocess.run")
    def test_not_found_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="No such container")
        assert check_docker_container("nonexistent") is False

    @patch("ops.health.subprocess.run")
    def test_timeout_returns_false(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=10)
        assert check_docker_container("gitea") is False

    @patch("ops.health.subprocess.run")
    def test_docker_not_installed_returns_false(self, mock_run):
        """docker binary absent → FileNotFoundError → False (not a crash)."""
        mock_run.side_effect = FileNotFoundError("docker not found")
        assert check_docker_container("gitea") is False

    @patch("ops.health.subprocess.run")
    def test_paused_container_returns_false(self, mock_run):
        """Status 'paused' must not be treated as 'running'."""
        mock_run.return_value = MagicMock(returncode=0, stdout="paused\n")
        assert check_docker_container("gitea") is False


class TestCheckDiskUsage:
    """STQA2-2.3: 4 tests for check_disk_usage (3 spec + 1 edge case)."""

    @patch("ops.health.shutil.disk_usage")
    def test_correct_values(self, mock_usage):
        # 500 GB used, 1 TB total.
        mock_usage.return_value = MagicMock(
            total=1024 ** 3 * 1000,
            used=1024 ** 3 * 500,
            free=1024 ** 3 * 500,
        )
        used, total, pct = check_disk_usage("/")
        assert total == 1000.0
        assert used == 500.0
        assert pct == 50.0

    @patch("ops.health.shutil.disk_usage")
    def test_permission_error_returns_zeros(self, mock_usage):
        mock_usage.side_effect = PermissionError("Access denied")
        assert check_disk_usage("/restricted") == (0.0, 0.0, 0.0)

    @patch("ops.health.shutil.disk_usage")
    def test_near_full_percent(self, mock_usage):
        # 950 GB used of 1 TB.
        mock_usage.return_value = MagicMock(
            total=1024 ** 3 * 1000,
            used=1024 ** 3 * 950,
            free=1024 ** 3 * 50,
        )
        used, total, pct = check_disk_usage("/")
        assert pct == 95.0
        assert used == 950.0

    @patch("ops.health.shutil.disk_usage")
    def test_oserror_returns_zeros(self, mock_usage):
        """OSError (e.g. path doesn't exist) must not propagate."""
        mock_usage.side_effect = OSError("No such file or directory")
        assert check_disk_usage("/nonexistent") == (0.0, 0.0, 0.0)


class TestCheckMemoryPressure:
    """STQA2-2.4: 4 tests for check_memory_pressure."""

    def test_with_psutil_installed(self):
        mock_mem = MagicMock()
        mock_mem.used = 8 * 1024 * 1024 * 1024  # 8 GB
        mock_mem.available = 24 * 1024 * 1024 * 1024  # 24 GB

        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = mock_mem

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            # Need to reimport to pick up the mock
            import importlib
            import ops.health

            importlib.reload(ops.health)
            used, available = ops.health.check_memory_pressure()

        # Reload back to normal
        import importlib
        import ops.health

        importlib.reload(ops.health)

        assert used == 8192
        assert available == 24576

    def test_psutil_import_error_returns_zeros(self):
        with patch.dict("sys.modules", {"psutil": None}):
            import importlib
            import ops.health

            importlib.reload(ops.health)
            result = ops.health.check_memory_pressure()

        import importlib
        import ops.health

        importlib.reload(ops.health)

        assert result == (0, 0)

    def test_psutil_exception_returns_zeros(self):
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.side_effect = RuntimeError("psutil error")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            import importlib
            import ops.health

            importlib.reload(ops.health)
            result = ops.health.check_memory_pressure()

        import importlib
        import ops.health

        importlib.reload(ops.health)

        assert result == (0, 0)

    def test_returns_tuple_of_ints(self):
        """Verify return type contract: both values are int."""
        used, available = check_memory_pressure()
        assert isinstance(used, int)
        assert isinstance(available, int)
