"""
ops.health — Testable health check functions for the soul-team infrastructure.

Provides 4 functions:
  - check_service_active(name) -> bool
  - check_docker_container(name) -> bool
  - check_disk_usage(path) -> tuple[float, float, float]
  - check_memory_pressure() -> tuple[int, int]

All functions handle exceptions gracefully — they NEVER raise.
Guardian v2 depends on this stability contract.
"""

import shutil
import subprocess
from typing import Tuple


_SUBPROCESS_TIMEOUT = 10  # seconds


def check_service_active(name: str) -> bool:
    """Check if a systemd service is active.

    Returns True if `systemctl is-active --quiet <name>` exits 0.
    Returns False for inactive, not-found, FileNotFoundError, or timeout.
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return result.returncode == 0
    except FileNotFoundError:
        # systemctl not available (e.g., macOS, container without systemd).
        return False
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_docker_container(name: str) -> bool:
    """Check if a Docker container is running.

    Returns True if `docker inspect` reports status "running".
    Returns False for exited, not-found, timeout, or any error.
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", name],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            return False
        return result.stdout.strip() == "running"
    except FileNotFoundError:
        # docker not installed.
        return False
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_disk_usage(path: str) -> Tuple[float, float, float]:
    """Check disk usage for the given path.

    Returns (used_gb, total_gb, percent).
    Returns (0.0, 0.0, 0.0) on PermissionError or any other failure.
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        percent = (usage.used / usage.total * 100) if usage.total > 0 else 0.0
        return (round(used_gb, 2), round(total_gb, 2), round(percent, 1))
    except PermissionError:
        return (0.0, 0.0, 0.0)
    except Exception:
        return (0.0, 0.0, 0.0)


def check_memory_pressure() -> Tuple[int, int]:
    """Check system memory pressure.

    Returns (used_mb, available_mb).
    Returns (0, 0) if psutil is not installed or any error occurs.
    """
    try:
        import psutil  # noqa: delayed import — optional dependency
        mem = psutil.virtual_memory()
        used_mb = int(mem.used / (1024 * 1024))
        available_mb = int(mem.available / (1024 * 1024))
        return (used_mb, available_mb)
    except ImportError:
        return (0, 0)
    except Exception:
        return (0, 0)
