#!/bin/bash
# soul-comms-status.sh — Health check for soul-team live communication components
# Checks: router service, all 10 sidecar PIDs, queue depths, active discussions
# Usage: soul-comms-status.sh

TEAM_DIR="$HOME/.clawteam/teams/soul-team"
SIDECAR_DIR="$TEAM_DIR/sidecar"
QUEUE_DIR="$TEAM_DIR/queue"
DISCUSSIONS_DIR="$TEAM_DIR/discussions"
AGENTS=(team-lead happy xavier hawkeye pepper fury loki shuri stark banner)

# ── Color support ─────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    GREEN='' RED='' YELLOW='' BOLD='' RESET=''
fi

ok()   { printf "${GREEN}● alive${RESET}"; }
dead() { printf "${RED}✗ dead${RESET}"; }
active_color()   { printf "${GREEN}● active${RESET}"; }
inactive_color() { printf "${RED}✗ inactive${RESET}"; }

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
printf "${BOLD}Soul Comms Status${RESET} [$(date '+%Y-%m-%d %H:%M:%S')]\n"
printf '═%.0s' {1..45}
echo ""
echo ""

# ── Router status ─────────────────────────────────────────────────────────────
printf "${BOLD}Router:${RESET}   "
router_state=$(systemctl --user is-active soul-router.service 2>/dev/null)
if [ "$router_state" = "active" ]; then
    active_color
    printf "  (soul-router.service)\n"
else
    inactive_color
    printf "  (soul-router.service: %s)\n" "$router_state"
fi
echo ""

# ── Sidecar status ────────────────────────────────────────────────────────────
printf "${BOLD}Sidecars:${RESET}\n"
sidecars_alive=0
sidecars_dead=0
for agent in "${AGENTS[@]}"; do
    pid_file="$SIDECAR_DIR/${agent}.pid"
    printf "  %-12s" "$agent"
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            ok
            printf "  (pid %s)\n" "$pid"
            sidecars_alive=$((sidecars_alive + 1))
        else
            dead
            printf "  (stale pid file: %s)\n" "${pid:-empty}"
            sidecars_dead=$((sidecars_dead + 1))
        fi
    else
        dead
        printf "  (no pid file)\n"
        sidecars_dead=$((sidecars_dead + 1))
    fi
done
printf "  ${BOLD}Total:${RESET} %d alive, %d dead\n" "$sidecars_alive" "$sidecars_dead"
echo ""

# ── Queue depths ──────────────────────────────────────────────────────────────
printf "${BOLD}Queue depths:${RESET}\n"
any_queued=false
for agent in "${AGENTS[@]}"; do
    queue_file="$QUEUE_DIR/${agent}.json"
    if [ -f "$queue_file" ]; then
        depth=$(jq '. | length' "$queue_file" 2>/dev/null || echo 0)
        if [ "$depth" -gt 0 ]; then
            printf "  ${YELLOW}%-12s %d message(s) pending${RESET}\n" "$agent:" "$depth"
            any_queued=true
        fi
    fi
done
if [ "$any_queued" = "false" ]; then
    printf "  All queues empty\n"
fi
echo ""

# ── Active discussions ────────────────────────────────────────────────────────
printf "${BOLD}Active discussions:${RESET} "
active_count=0
active_threads=()
if [ -d "$DISCUSSIONS_DIR" ]; then
    for thread_dir in "$DISCUSSIONS_DIR"/*/; do
        [ -d "$thread_dir" ] || continue
        state_file="$thread_dir/state.json"
        [ -f "$state_file" ] || continue
        status=$(jq -r '.status // ""' "$state_file" 2>/dev/null)
        if [ "$status" = "active" ]; then
            thread_id=$(jq -r '.thread_id // "unknown"' "$state_file" 2>/dev/null)
            msg_count=$(jq -r '.message_count // 0' "$state_file" 2>/dev/null)
            active_threads+=("$thread_id ($msg_count messages)")
            active_count=$((active_count + 1))
        fi
    done
fi
printf "%d\n" "$active_count"
for t in "${active_threads[@]}"; do
    printf "  - %s\n" "$t"
done
echo ""
