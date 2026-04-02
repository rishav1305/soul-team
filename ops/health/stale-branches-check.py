#!/usr/bin/env python3
"""
stale-branches-check.py -- Flag git branches >7 days stale in soul-v2.

Runs 'git branch -a --sort=-committerdate' and identifies branches with
last commit older than 7 days. Writes to ~/.soul/health/stale-branches.json.

Author: Banner (Data Science, Soul Team)
Date: 2026-03-30
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SOUL_V2_DIR = Path.home() / "soul-v2"
OUTPUT_FILE = Path.home() / ".soul" / "health" / "stale-branches.json"
STALE_THRESHOLD_DAYS = 7
TIMEOUT_SECONDS = 60


def get_branches() -> list[dict]:
    """Get all branches with their last commit date."""
    branches = []

    try:
        # Get branch names and dates using git for-each-ref
        proc = subprocess.run(
            ["git", "for-each-ref", "--sort=-committerdate",
             "--format=%(refname:short)\t%(committerdate:iso8601)\t%(subject)",
             "refs/heads/", "refs/remotes/"],
            cwd=str(SOUL_V2_DIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )

        if proc.returncode != 0:
            return []

        for line in proc.stdout.strip().splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                name = parts[0]
                date_str = parts[1]
                subject = parts[2] if len(parts) > 2 else ""

                # Skip HEAD refs
                if name == "origin/HEAD":
                    continue

                try:
                    # Parse ISO date (e.g., "2026-03-25 14:30:00 +0530")
                    commit_date = datetime.fromisoformat(date_str.strip())
                    age_days = (datetime.now(commit_date.tzinfo) - commit_date).days
                    branches.append({
                        "branch": name,
                        "last_commit": date_str.strip()[:19],
                        "age_days": age_days,
                        "subject": subject[:100],
                        "stale": age_days > STALE_THRESHOLD_DAYS,
                    })
                except (ValueError, TypeError):
                    branches.append({
                        "branch": name,
                        "last_commit": date_str,
                        "age_days": -1,
                        "subject": subject[:100],
                        "stale": False,
                    })

    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    return branches


def main():
    report = {
        "check": "stale-branches",
        "timestamp": datetime.now().isoformat()[:19],
        "threshold_days": STALE_THRESHOLD_DAYS,
        "status": "unknown",
        "total_branches": 0,
        "stale_count": 0,
        "branches": [],
        "stale_branches": [],
    }

    if not SOUL_V2_DIR.exists():
        report["status"] = "error"
        report["errors"] = [f"soul-v2 not found: {SOUL_V2_DIR}"]
    else:
        branches = get_branches()
        stale = [b for b in branches if b["stale"]]

        report["status"] = "ok"
        report["total_branches"] = len(branches)
        report["stale_count"] = len(stale)
        report["branches"] = branches[:100]  # Cap output
        report["stale_branches"] = stale

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    stale_count = report["stale_count"]
    total = report["total_branches"]
    print(f"[{'WARN' if stale_count > 0 else 'OK'}] stale-branches: "
          f"{stale_count}/{total} branches stale (>{STALE_THRESHOLD_DAYS} days)")

    if stale_count > 0:
        for b in report["stale_branches"][:10]:
            print(f"  {b['branch']}: {b['age_days']} days old")

    sys.exit(0)


if __name__ == "__main__":
    main()
