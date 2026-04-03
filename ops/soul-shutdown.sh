#!/bin/bash
# soul-shutdown — Graceful shutdown protocol for power failure
# Usage: soul-shutdown [reason]
# Saves state, kills agents, stops services, shuts down both machines

REASON="${1:-Power failure - manual trigger}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="$HOME/soul-roles/shared/briefs/sentinel-power-log.md"
STATE_FILE="$HOME/soul-roles/shared/briefs/sentinel-state-dump.md"
TITAN_PC="${SOUL_WORKER_SSH:-user@worker-host}"

echo "=== SOUL SHUTDOWN PROTOCOL ==="
echo "Reason: $REASON"
echo ""

# 1. LOG
echo ">> Step 1/6: Logging event..."
mkdir -p "$(dirname "$LOG_FILE")"
cat >> "$LOG_FILE" << EOF

---
## $TIMESTAMP
**Event:** Shutdown protocol triggered
**Reason:** $REASON
**Active session:** $(tmux has-session -t soul-team 2>/dev/null && echo "soul-team running" || echo "no soul-team session")
EOF
echo "   Logged to $LOG_FILE"

# 2. SAVE STATE
echo ">> Step 2/6: Saving state..."
{
  echo "---"
  echo "## State Dump: $TIMESTAMP"
  echo ""
  echo "### tmux sessions"
  tmux list-sessions 2>/dev/null || echo "No tmux sessions"
  echo ""
  echo "### soul-team panes"
  tmux list-panes -t soul-team -F '#{pane_index}: #{pane_current_command} (#{pane_pid})' 2>/dev/null || echo "No soul-team session"
  echo ""
  echo "### Running claude processes"
  pgrep -af claude 2>/dev/null | head -10 || echo "None"
  echo ""
  echo "### Service status"
  systemctl is-active soul-v2 2>/dev/null && echo "soul-v2: running" || echo "soul-v2: stopped"
  echo ""
  echo "### worker reachable"
  WORKER_HOST="${SOUL_WORKER_HOST:-worker-host}"
  ping -c 1 -W 2 "$WORKER_HOST" >/dev/null 2>&1 && echo "worker: UP" || echo "worker: DOWN"
  echo ""
} >> "$STATE_FILE"
echo "   State saved to $STATE_FILE"

# 3. KILL SIDECARS + ROUTER (before killing tmux session)
echo ">> Step 3/6: Stopping live comms (sidecars + router)..."
SIDECAR_DIR="$HOME/.clawteam/teams/soul-team/sidecar"
sidecar_count=0
if [ -d "$SIDECAR_DIR" ]; then
  for pid_file in "$SIDECAR_DIR"/*.pid; do
    [ -f "$pid_file" ] || continue
    pid=$(cat "$pid_file" 2>/dev/null)
    agent=$(basename "${pid_file%.pid}")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      echo "   Sidecar killed: $agent (PID=$pid)"
      sidecar_count=$((sidecar_count + 1))
    fi
    rm -f "$pid_file"
  done
fi
echo "   $sidecar_count sidecars stopped"

echo "   Stopping soul-router.service..."
systemctl --user stop soul-router.service 2>/dev/null && \
  echo "   soul-router.service stopped" || \
  echo "   soul-router.service was not running"

# 3b. KILL TMUX TEAM SESSION
echo ">> Step 3b/6: Stopping soul-team..."
if tmux has-session -t soul-team 2>/dev/null; then
  tmux kill-session -t soul-team
  echo "   soul-team session killed"
else
  echo "   No soul-team session found (skipping)"
fi

# 4. STOP SERVICES
echo ">> Step 4/6: Stopping services..."
sudo systemctl stop soul-v2 2>/dev/null && echo "   soul-v2 stopped" || echo "   soul-v2 was not running"

# 5. SHUTDOWN TITAN-PC
echo ">> Step 5/6: Shutting down worker..."
WORKER_IP="${SOUL_WORKER_HOST:-worker-host}"
if ping -c 1 -W 2 "$WORKER_IP" >/dev/null 2>&1; then
  ssh -o ConnectTimeout=5 "$TITAN_PC" "sudo shutdown now" 2>/dev/null
  echo "   worker shutdown initiated"
else
  echo "   worker unreachable (already down or disconnected)"
fi

# 6. SHUTDOWN TITAN-PI
echo ">> Step 6/6: Shutting down primary in 5 seconds..."
echo "   (Ctrl+C to abort)"
sleep 5
sudo shutdown now
