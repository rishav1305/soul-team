#!/usr/bin/env python3
"""
services-check.py -- Check systemctl status for Soul services.

Checks soul-v2, soul-guardian, soul-courier, soul-router services.
Writes status to ~/.soul/health/services.json.

Author: Banner (Data Science, Soul Team)
Date: 2026-03-30
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_FILE = Path.home() / ".soul" / "health" / "services.json"
TIMEOUT_SECONDS = 30

# Service definitions: (name, user_service)
# soul-v2 is a SYSTEM service on titan-pi (not titan-pc) — skipped here.
# soul-guardian, soul-courier, soul-router are USER services on titan-pc.
SERVICES = [
    ("soul-guardian", True),   # user service on titan-pc
    ("soul-courier", True),    # user service on titan-pc
    ("soul-router", True),     # user service on titan-pc
    # ("soul-v2", False),      # system service on titan-pi only — not checked from titan-pc
]


def check_service(name: str, user_service: bool = False) -> dict:
    """Check a single systemd service. Uses --user flag for user services."""
    result = {
        "service": name,
        "scope": "user" if user_service else "system",
        "status": "unknown",
        "active": False,
        "sub_state": "",
        "pid": None,
        "uptime": "",
        "memory": "",
        "errors": [],
    }

    try:
        # Check if service exists and get status
        cmd = ["systemctl"]
        if user_service:
            cmd.append("--user")
        cmd.extend(["show", name,
             "--property=ActiveState,SubState,MainPID,MemoryCurrent,StatusText"])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        if proc.returncode != 0:
            result["status"] = "not-found"
            result["errors"] = [f"systemctl show failed: {proc.stderr.strip()[:200]}"]
            return result

        props = {}
        for line in proc.stdout.strip().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                props[key.strip()] = value.strip()

        active_state = props.get("ActiveState", "unknown")
        sub_state = props.get("SubState", "unknown")
        pid = props.get("MainPID", "0")
        memory = props.get("MemoryCurrent", "")

        result["status"] = active_state
        result["active"] = active_state == "active"
        result["sub_state"] = sub_state

        if pid and pid != "0":
            result["pid"] = int(pid)

        # Format memory
        if memory and memory != "[not set]":
            try:
                mem_bytes = int(memory)
                if mem_bytes >= 1024 * 1024 * 1024:
                    result["memory"] = f"{mem_bytes / 1024 / 1024 / 1024:.1f} GB"
                elif mem_bytes >= 1024 * 1024:
                    result["memory"] = f"{mem_bytes / 1024 / 1024:.1f} MB"
                elif mem_bytes >= 1024:
                    result["memory"] = f"{mem_bytes / 1024:.1f} KB"
                else:
                    result["memory"] = f"{mem_bytes} B"
            except ValueError:
                result["memory"] = memory

        # Get uptime from ActiveEnterTimestamp
        cmd2 = ["systemctl"]
        if user_service:
            cmd2.append("--user")
        cmd2.extend(["show", name, "--property=ActiveEnterTimestamp"])
        proc2 = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if proc2.returncode == 0:
            ts_line = proc2.stdout.strip()
            if "=" in ts_line:
                ts_str = ts_line.split("=", 1)[1].strip()
                if ts_str:
                    result["uptime"] = ts_str

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["errors"] = [f"systemctl timed out after {TIMEOUT_SECONDS}s"]
    except FileNotFoundError:
        result["status"] = "error"
        result["errors"] = ["systemctl not found"]
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]

    return result


def main():
    report = {
        "check": "services",
        "timestamp": datetime.now().isoformat()[:19],
        "status": "unknown",
        "services": [],
        "active_count": 0,
        "total_count": 0,
    }

    for name, is_user in SERVICES:
        svc = check_service(name, user_service=is_user)
        report["services"].append(svc)

    report["active_count"] = sum(1 for s in report["services"] if s["active"])
    report["total_count"] = len(SERVICES)
    report["status"] = "ok" if report["active_count"] == report["total_count"] else "degraded"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    label = "OK" if report["status"] == "ok" else "WARN"
    print(f"[{label}] services: {report['active_count']}/{report['total_count']} active")
    for svc in report["services"]:
        icon = "UP" if svc["active"] else "DOWN"
        mem = f" ({svc['memory']})" if svc["memory"] else ""
        print(f"  [{icon}] {svc['service']}: {svc['status']}/{svc['sub_state']}{mem}")

    sys.exit(0 if report["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
