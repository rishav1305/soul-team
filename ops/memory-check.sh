#!/bin/bash
# memory-check.sh -- Daily agent memory size enforcement
#
# Reports agent memory sizes and alerts when any agent exceeds 100KB.
# Designed to run from cron (daily at 06:00) or manually.
#
# Alerts are written to:
#   1. Guardian log (~/.soul/guardian.log)
#   2. CEO inbox (via soul-msg if available)

set -euo pipefail

MEMORY_BASE="$HOME/.claude/agent-memory"
GUARDIAN_LOG="$HOME/.soul/guardian.log"
THRESHOLD_KB=100
SOUL_MSG="/usr/local/bin/soul-msg"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S")

log_guardian() {
    local msg="$1"
    local line="[$TIMESTAMP] [INFO] [memory-check] $msg"
    echo "$line"
    mkdir -p "$(dirname "$GUARDIAN_LOG")"
    echo "$line" >> "$GUARDIAN_LOG"
}

alert() {
    local msg="$1"
    local line="[$TIMESTAMP] [WARN] [memory-check] $msg"
    echo "$line"
    mkdir -p "$(dirname "$GUARDIAN_LOG")"
    echo "$line" >> "$GUARDIAN_LOG"
    # Send to CEO inbox if soul-msg is available
    if [ -x "$SOUL_MSG" ]; then
        "$SOUL_MSG" send team-lead "[MEMORY-CHECK] $msg" --priority P2 2>/dev/null || true
    fi
}

if [ ! -d "$MEMORY_BASE" ]; then
    log_guardian "No agent memory directory found at $MEMORY_BASE"
    exit 0
fi

log_guardian "Memory size report:"

violations=0
while IFS=$'\t' read -r size_str dir_path; do
    agent=$(basename "$dir_path")
    size_kb=$(du -sk "$dir_path" 2>/dev/null | cut -f1)
    log_guardian "  $agent: ${size_str} (${size_kb}KB)"

    if [ "$size_kb" -gt "$THRESHOLD_KB" ]; then
        alert "$agent memory exceeds ${THRESHOLD_KB}KB: ${size_kb}KB (${size_str})"
        violations=$((violations + 1))
    fi
done < <(du -sh "$MEMORY_BASE"/*/ 2>/dev/null)

if [ "$violations" -eq 0 ]; then
    log_guardian "All agents within ${THRESHOLD_KB}KB limit."
else
    log_guardian "$violations agent(s) exceed ${THRESHOLD_KB}KB limit."
fi
