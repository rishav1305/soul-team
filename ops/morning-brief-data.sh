#!/bin/bash
# morning-brief-data.sh — Gather all data Friday needs for the morning brief
#
# Outputs to ~/.soul/preflight/morning-brief.txt
# Designed for crontab: 30 5 * * *
#
# Token optimization: Friday reads one file instead of running 10+ commands.

set -euo pipefail

PREFLIGHT_DIR="$HOME/.soul/preflight"
INBOX_ROOT="$HOME/soul-roles/shared/inbox"
BRIEFS_DIR="$HOME/soul-roles/shared/briefs"
BACKLOG_CLI="$HOME/.claude/skills/pa-backlog/backlog_cli.py"
HEALTH_SCRIPT="$HOME/.local/bin/soul-health"
GUARDIAN_DB="$HOME/.soul/guardian.db"
SOUL_BOARD="$HOME/.local/bin/soul-board"

mkdir -p "$PREFLIGHT_DIR"

OUT="$PREFLIGHT_DIR/morning-brief.txt"
TS=$(date '+%Y-%m-%d %H:%M:%S IST')

{
    echo "########################################"
    echo "# MORNING BRIEF DATA"
    echo "# Generated: ${TS}"
    echo "########################################"
    echo ""

    # ── 1. Agent Inbox Counts ──────────────────────────────────────────────
    echo "## INBOX COUNTS"
    ALL_AGENTS="happy xavier hawkeye pepper fury loki shuri stark banner friday"
    total_inbox=0
    for agent in $ALL_AGENTS; do
        inbox_dir="${INBOX_ROOT}/${agent}"
        if [ -d "$inbox_dir" ]; then
            count=$(find "$inbox_dir" -maxdepth 1 -name "*.md" -type f 2>/dev/null | wc -l)
            if [ "$count" -gt 0 ]; then
                echo "  ${agent}: ${count} file(s)"
                total_inbox=$((total_inbox + count))
            fi
        fi
    done
    if [ "$total_inbox" -eq 0 ]; then
        echo "  All inboxes empty."
    else
        echo "  TOTAL: ${total_inbox}"
    fi
    echo ""

    # ── 2. Backlog Dashboard ────────────────────────────────────────────────
    echo "## BACKLOG DASHBOARD"
    if [ -f "$BACKLOG_CLI" ]; then
        python3 "$BACKLOG_CLI" dashboard 2>/dev/null || echo "  Backlog CLI returned error."
    else
        echo "  Backlog CLI not found at $BACKLOG_CLI"
    fi
    echo ""

    # ── 3. Health Summary ───────────────────────────────────────────────────
    echo "## HEALTH SUMMARY"
    if [ -x "$HEALTH_SCRIPT" ]; then
        bash "$HEALTH_SCRIPT" --compact 2>/dev/null || bash "$HEALTH_SCRIPT" 2>/dev/null | head -30 || echo "  Health script failed."
    else
        # Fallback: read health JSON files directly
        for hf in "$HOME/.soul/health/verify-static.json" "$HOME/.soul/health/services.json"; do
            if [ -f "$hf" ]; then
                echo "  $(basename "$hf"):"
                python3 -c "
import json
try:
    d = json.load(open('$hf'))
    ts = d.get('timestamp', d.get('checked_at', 'unknown'))
    status = d.get('status', d.get('overall', 'unknown'))
    print(f'    status: {status}, updated: {ts}')
except Exception as e:
    print(f'    error: {e}')
" 2>/dev/null
            fi
        done
    fi
    echo ""

    # ── 4. Today's Spend ────────────────────────────────────────────────────
    echo "## TODAY'S SPEND"
    if [ -f "$GUARDIAN_DB" ]; then
        sqlite3 "$GUARDIAN_DB" "SELECT agent, printf('\$%.4f', total_cost) as cost FROM daily_spend WHERE date = date('now') ORDER BY total_cost DESC;" 2>/dev/null || echo "  No spend data for today."
    else
        echo "  Guardian DB not found."
    fi
    echo ""

    # ── 5. Agent Board ──────────────────────────────────────────────────────
    echo "## AGENT BOARD"
    if [ -x "$SOUL_BOARD" ]; then
        "$SOUL_BOARD" --compact 2>/dev/null || echo "  soul-board returned error."
    else
        # Fallback: read heartbeat files
        echo "  (soul-board not found, reading heartbeats directly)"
        for agent in $ALL_AGENTS; do
            hb="$HOME/.local/share/assistant/heartbeat/${agent}.json"
            if [ -f "$hb" ]; then
                python3 -c "
import json
try:
    d = json.load(open('$hb'))
    s = d.get('status', '?')
    t = d.get('task', d.get('current_task', ''))
    print(f'  {\"$agent\":12s} {s:10s} {t}')
except:
    print(f'  {\"$agent\":12s} error')
" 2>/dev/null
            fi
        done
    fi
    echo ""

    # ── 6. Recent Briefs (last 24h) ────────────────────────────────────────
    echo "## RECENT BRIEFS (last 24h)"
    recent=$(find "$BRIEFS_DIR" -name "*.md" -mtime -1 -printf "%T+ %p\n" 2>/dev/null | sort -r | head -10)
    if [ -n "$recent" ]; then
        echo "$recent" | while read -r ts_path; do
            filepath=$(echo "$ts_path" | cut -d' ' -f2-)
            echo "  - $(basename "$filepath")"
        done
    else
        echo "  No briefs in last 24 hours."
    fi
    echo ""

    # ── 7. Overdue Tasks ───────────────────────────────────────────────────
    echo "## OVERDUE TASKS"
    if [ -f "$BACKLOG_CLI" ]; then
        python3 "$BACKLOG_CLI" query --status open --overdue 2>/dev/null || echo "  No overdue tasks (or flag not supported)."
    else
        echo "  Backlog CLI not found."
    fi
    echo ""

    echo "########################################"
    echo "# END MORNING BRIEF"
    echo "########################################"

} > "$OUT"

echo "Morning brief written: $OUT"
