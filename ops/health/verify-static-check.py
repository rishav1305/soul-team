#!/usr/bin/env python3
"""
verify-static-check.py -- Run 'make verify-static' on soul-v2 and report result.

Writes pass/fail + timestamp + errors to ~/.soul/health/verify-static.json.
Designed for cron execution. Accounts for sshfs latency (180s+ timeout).

Author: Banner (Data Science, Soul Team)
Date: 2026-03-30
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOUL_V2_DIR = Path.home() / "soul-v2"
OUTPUT_FILE = Path.home() / ".soul" / "health" / "verify-static.json"
TIMEOUT_SECONDS = 300  # 5 min — sshfs can be slow


def run_check() -> dict:
    """Run make verify-static and capture result."""
    result = {
        "check": "verify-static",
        "timestamp": datetime.now().isoformat()[:19],
        "status": "unknown",
        "duration_s": 0,
        "errors": [],
        "output": "",
    }

    if not SOUL_V2_DIR.exists():
        result["status"] = "error"
        result["errors"] = [f"soul-v2 directory not found: {SOUL_V2_DIR}"]
        return result

    # Check if Makefile exists
    makefile = SOUL_V2_DIR / "Makefile"
    if not makefile.exists():
        result["status"] = "error"
        result["errors"] = [f"Makefile not found in {SOUL_V2_DIR}"]
        return result

    start = datetime.now()
    try:
        proc = subprocess.run(
            ["make", "verify-static"],
            cwd=str(SOUL_V2_DIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**os.environ, "PATH": f"/usr/bin:{os.environ.get('PATH', '')}"},
        )
        elapsed = (datetime.now() - start).total_seconds()
        result["duration_s"] = round(elapsed, 1)
        result["output"] = proc.stdout[-2000:] if proc.stdout else ""

        if proc.returncode == 0:
            result["status"] = "pass"
        else:
            result["status"] = "fail"
            stderr = proc.stderr.strip() if proc.stderr else ""
            if stderr:
                # Extract meaningful error lines (skip noise)
                errors = [
                    line for line in stderr.splitlines()
                    if line.strip() and not line.startswith("make[")
                ]
                result["errors"] = errors[-20:]  # Last 20 error lines

    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start).total_seconds()
        result["duration_s"] = round(elapsed, 1)
        result["status"] = "timeout"
        result["errors"] = [f"Command timed out after {TIMEOUT_SECONDS}s"]

    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]

    return result


def main():
    result = run_check()

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write result
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    # Also print for cron log
    status_icon = {"pass": "OK", "fail": "FAIL", "timeout": "TIMEOUT", "error": "ERROR"}.get(
        result["status"], "?"
    )
    print(f"[{status_icon}] verify-static: {result['status']} ({result['duration_s']}s)")
    if result["errors"]:
        for e in result["errors"][:5]:
            print(f"  {e}")

    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
