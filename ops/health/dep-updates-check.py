#!/usr/bin/env python3
"""
dep-updates-check.py -- Check Go and npm dependency updates for soul-v2.

Runs 'go list -m -u all' and 'npm outdated --json', writes combined report
to ~/.soul/health/dep-updates.json. Uses /usr/bin/go (or go on PATH).

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
WEB_DIR = SOUL_V2_DIR / "web"
OUTPUT_FILE = Path.home() / ".soul" / "health" / "dep-updates.json"
GO_BIN = "/usr/bin/go"
TIMEOUT_SECONDS = 120


def check_go_updates() -> dict:
    """Run go list -m -u all and parse updates."""
    result = {"status": "unknown", "updates_available": 0, "modules": [], "errors": []}

    if not os.path.exists(GO_BIN):
        result["status"] = "skip"
        result["errors"] = [f"Go binary not found at {GO_BIN}"]
        return result

    go_mod = SOUL_V2_DIR / "go.mod"
    if not go_mod.exists():
        result["status"] = "skip"
        result["errors"] = ["go.mod not found in soul-v2"]
        return result

    try:
        proc = subprocess.run(
            [GO_BIN, "list", "-m", "-u", "all"],
            cwd=str(SOUL_V2_DIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**os.environ, "GOPATH": os.environ.get("GOPATH", str(Path.home() / "go"))},
        )

        updates = []
        for line in proc.stdout.splitlines():
            # Lines with updates look like: module v1.0.0 [v1.1.0]
            if "[" in line and "]" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    module = parts[0]
                    current = parts[1]
                    available = parts[2].strip("[]")
                    updates.append({
                        "module": module,
                        "current": current,
                        "available": available,
                    })

        result["status"] = "ok"
        result["updates_available"] = len(updates)
        result["modules"] = updates[:50]  # Cap at 50

        if proc.returncode != 0 and proc.stderr:
            result["errors"] = [proc.stderr.strip()[:500]]

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["errors"] = [f"go list timed out after {TIMEOUT_SECONDS}s"]
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]

    return result


def check_npm_updates() -> dict:
    """Run npm outdated --json and parse."""
    result = {"status": "unknown", "updates_available": 0, "packages": [], "errors": []}

    if not WEB_DIR.exists():
        result["status"] = "skip"
        result["errors"] = [f"web directory not found: {WEB_DIR}"]
        return result

    package_json = WEB_DIR / "package.json"
    if not package_json.exists():
        result["status"] = "skip"
        result["errors"] = ["package.json not found in soul-v2/web"]
        return result

    try:
        proc = subprocess.run(
            ["npm", "outdated", "--json"],
            cwd=str(WEB_DIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        # npm outdated returns exit code 1 when outdated packages exist
        if proc.stdout.strip():
            try:
                outdated = json.loads(proc.stdout)
                packages = []
                for name, info in outdated.items():
                    packages.append({
                        "package": name,
                        "current": info.get("current", "?"),
                        "wanted": info.get("wanted", "?"),
                        "latest": info.get("latest", "?"),
                        "type": info.get("type", "?"),
                    })
                result["status"] = "ok"
                result["updates_available"] = len(packages)
                result["packages"] = packages[:50]
            except json.JSONDecodeError:
                result["status"] = "error"
                result["errors"] = ["Failed to parse npm outdated JSON output"]
        else:
            result["status"] = "ok"
            result["updates_available"] = 0

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["errors"] = [f"npm outdated timed out after {TIMEOUT_SECONDS}s"]
    except FileNotFoundError:
        result["status"] = "skip"
        result["errors"] = ["npm not found in PATH"]
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]

    return result


def main():
    report = {
        "check": "dep-updates",
        "timestamp": datetime.now().isoformat()[:19],
        "go": check_go_updates(),
        "npm": check_npm_updates(),
    }

    # Summary
    total_updates = report["go"]["updates_available"] + report["npm"]["updates_available"]
    report["total_updates"] = total_updates
    report["status"] = "ok" if all(
        r["status"] in ("ok", "skip") for r in [report["go"], report["npm"]]
    ) else "error"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[{'OK' if report['status'] == 'ok' else 'ERR'}] dep-updates: "
          f"{total_updates} updates (Go: {report['go']['updates_available']}, "
          f"npm: {report['npm']['updates_available']})")

    sys.exit(0 if report["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
