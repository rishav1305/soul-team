#!/usr/bin/env bash
# soul-heartbeat.sh — Writes a heartbeat JSON every 30s to ~/.clawteam/heartbeat/
#
# Purpose: Guardian reads heartbeat files to detect cross-machine connectivity.
# If the worker heartbeat goes stale (>60s), guardian marks those agents unreachable.
#
# Run as: background subshell launched by soul-team.sh
#   ( $HOME/.claude/scripts/soul-heartbeat.sh & )
#
# Writes: ~/.clawteam/heartbeat/{hostname}.json
# Format: {"ts": "ISO8601", "hostname": "<hostname>", "agents": ["agent1", ...]}

set -euo pipefail

HEARTBEAT_DIR="${HOME}/.clawteam/heartbeat"
HOSTNAME_SHORT=$(hostname -s)
INTERVAL=30

mkdir -p "$HEARTBEAT_DIR"

log() {
    echo "[soul-heartbeat] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2
}

get_active_agents() {
    # Returns comma-separated list of agent names with active tmux panes
    # Looks for panes whose title or process matches known agent names
    local agents=()
    local all_agents=(happy xavier hawkeye pepper fury loki shuri stark banner)

    for agent in "${all_agents[@]}"; do
        # Check if a tmux window or pane is named after this agent
        if tmux list-panes -a -F "#{pane_title}" 2>/dev/null | grep -qi "^${agent}$"; then
            agents+=("$agent")
        elif tmux list-windows -a -F "#{window_name}" 2>/dev/null | grep -qi "^${agent}$"; then
            agents+=("$agent")
        fi
    done

    # Return as JSON array
    if [ ${#agents[@]} -eq 0 ]; then
        echo "[]"
    else
        local json="["
        for i in "${!agents[@]}"; do
            if [ $i -gt 0 ]; then json+=","; fi
            json+="\"${agents[$i]}\""
        done
        json+="]"
        echo "$json"
    fi
}

write_heartbeat() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local agents_json
    agents_json=$(get_active_agents)

    local tmp="${HEARTBEAT_DIR}/.${HOSTNAME_SHORT}.tmp"
    local target="${HEARTBEAT_DIR}/${HOSTNAME_SHORT}.json"

    cat > "$tmp" <<EOF
{"ts": "${ts}", "hostname": "${HOSTNAME_SHORT}", "agents": ${agents_json}}
EOF
    mv "$tmp" "$target"
}

log "starting on ${HOSTNAME_SHORT}, writing to ${HEARTBEAT_DIR}/${HOSTNAME_SHORT}.json every ${INTERVAL}s"

# Write once immediately, then loop
write_heartbeat
log "initial heartbeat written"

while true; do
    sleep "$INTERVAL"
    write_heartbeat
done
