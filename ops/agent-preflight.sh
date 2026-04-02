#!/bin/bash
# agent-preflight.sh — Gather agent context into a single preflight file
#
# Usage:
#   ./agent-preflight.sh {agent_name}        # Single agent
#   ./agent-preflight.sh --all               # All known agents
#
# Output: ~/.soul/preflight/{agent}.txt
#
# Token optimization: agents read one file instead of running 5+ separate commands.

set -euo pipefail

PREFLIGHT_DIR="$HOME/.soul/preflight"
INBOX_ROOT="$HOME/soul-roles/shared/inbox"
BRIEFS_DIR="$HOME/soul-roles/shared/briefs"
HEARTBEAT_DIR="$HOME/.local/share/assistant/heartbeat"
BACKLOG_CLI="$HOME/.claude/skills/pa-backlog/backlog_cli.py"

ALL_AGENTS="happy xavier hawkeye pepper fury loki shuri stark banner friday"

mkdir -p "$PREFLIGHT_DIR"

gather_agent() {
    local agent="$1"
    local out="$PREFLIGHT_DIR/${agent}.txt"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S IST')

    {
        echo "======================================"
        echo "PREFLIGHT: ${agent}"
        echo "Generated: ${ts}"
        echo "======================================"
        echo ""

        # -- Inbox --
        echo "## INBOX"
        local inbox_dir="${INBOX_ROOT}/${agent}"
        if [ -d "$inbox_dir" ]; then
            local count
            count=$(find "$inbox_dir" -maxdepth 1 -name "*.md" -type f 2>/dev/null | wc -l)
            echo "  Files: ${count}"
            if [ "$count" -gt 0 ]; then
                echo "  Recent:"
                ls -t "$inbox_dir"/*.md 2>/dev/null | head -5 | while read -r f; do
                    echo "    - $(basename "$f")"
                done
            fi
        else
            echo "  No inbox directory."
        fi
        echo ""

        # -- Backlog --
        echo "## BACKLOG"
        if [ -f "$BACKLOG_CLI" ]; then
            python3 "$BACKLOG_CLI" query --status open --project "$agent" 2>/dev/null || echo "  No open tasks."
        else
            echo "  Backlog CLI not found."
        fi
        echo ""

        # -- Health --
        echo "## HEALTH"
        local health_files=("$HOME/.soul/health/verify-static.json" "$HOME/.soul/health/services.json")
        local found_health=false
        for hf in "${health_files[@]}"; do
            if [ -f "$hf" ]; then
                echo "  $(basename "$hf"):"
                # Extract key fields (compact summary)
                python3 -c "
import json, sys
try:
    d = json.load(open('$hf'))
    ts = d.get('timestamp', d.get('checked_at', 'unknown'))
    status = d.get('status', d.get('overall', 'unknown'))
    print(f'    status: {status}, updated: {ts}')
except Exception as e:
    print(f'    error reading: {e}')
" 2>/dev/null
                found_health=true
            fi
        done
        if ! $found_health; then
            echo "  No health data available."
        fi
        echo ""

        # -- Heartbeat --
        echo "## HEARTBEAT"
        local hb_file="${HEARTBEAT_DIR}/${agent}.json"
        if [ -f "$hb_file" ]; then
            python3 -c "
import json, sys
try:
    d = json.load(open('$hb_file'))
    status = d.get('status', 'unknown')
    task = d.get('task', d.get('current_task', ''))
    ts = d.get('timestamp', d.get('updated_at', 'unknown'))
    print(f'  Status: {status}')
    if task: print(f'  Task: {task}')
    print(f'  Last update: {ts}')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null
        else
            echo "  No heartbeat file."
        fi
        echo ""

        # -- Recent Briefs --
        echo "## RECENT BRIEFS"
        local briefs
        briefs=$(ls -t "${BRIEFS_DIR}/${agent}-"* 2>/dev/null | head -3)
        if [ -n "$briefs" ]; then
            echo "$briefs" | while read -r f; do
                echo "  - $(basename "$f") ($(stat -c '%y' "$f" 2>/dev/null | cut -d' ' -f1))"
            done
        else
            echo "  No recent briefs."
        fi
        echo ""
        echo "======================================"

    } > "$out"

    echo "Preflight written: $out"
}

# Parse args
if [ $# -eq 0 ]; then
    echo "Usage: $0 {agent_name} | --all"
    exit 1
fi

if [ "$1" = "--all" ]; then
    for agent in $ALL_AGENTS; do
        gather_agent "$agent"
    done
    echo "All preflight files generated in $PREFLIGHT_DIR/"
else
    gather_agent "$1"
fi
