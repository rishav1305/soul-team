#!/usr/bin/env bash
# setup-remote.sh — Provision a remote machine for soul-team agent execution
#
# Called by: soul-team setup-remote <machine-name>
# Or directly: bash ops/setup-remote.sh <ssh-target> <repo-url> <primary-host>
#
# This script:
#   1. Verifies SSH connectivity and prerequisites on the remote
#   2. Clones (or pulls) the soul-team repo on the remote
#   3. Runs setup.sh on the remote
#   4. Installs sshfs and creates mount points for shared comms
#   5. Generates and installs a systemd mount service on the remote
#   6. Copies config to the remote
#   7. Runs a verification suite
#
# Requires: ssh, sshfs (installed on remote), git (on remote)
# Idempotent: safe to re-run.

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  [ok] $*${NC}"; }
warn() { echo -e "${YELLOW}  [!!] $*${NC}"; }
fail() { echo -e "${RED}  [FAIL] $*${NC}"; }
info() { echo -e "  ${BOLD}$*${NC}"; }
step() { echo -e "\n${BOLD}--- Step $1: $2 ---${NC}"; }

# ── Parse arguments ──────────────────────────────────────────────────────────

SSH_TARGET="${1:-}"
REPO_URL="${2:-ssh://git@git.titan.local:222/admin/soul-team.git}"
PRIMARY_HOST="${3:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
PRIMARY_USER="${4:-$(whoami)}"
CONFIG_FILE="${5:-${HOME}/.soul-team/config.toml}"

if [[ -z "$SSH_TARGET" ]]; then
    echo "Usage: setup-remote.sh <ssh-target> [repo-url] [primary-host] [primary-user] [config-file]"
    echo ""
    echo "  ssh-target:   user@host (e.g. rishav@192.168.0.196)"
    echo "  repo-url:     Git repo URL (default: Gitea soul-team)"
    echo "  primary-host: IP of the primary machine (default: auto-detect)"
    echo "  primary-user: Username on primary machine (default: current user)"
    echo "  config-file:  Path to config.toml to copy (default: ~/.soul-team/config.toml)"
    exit 1
fi

REMOTE_USER="${SSH_TARGET%%@*}"
REMOTE_HOST="${SSH_TARGET#*@}"

echo ""
echo -e "${BOLD}soul-team remote setup${NC}"
echo "=========================================="
echo -e "  Target:  ${BOLD}${SSH_TARGET}${NC}"
echo -e "  Repo:    ${DIM}${REPO_URL}${NC}"
echo -e "  Primary: ${DIM}${PRIMARY_USER}@${PRIMARY_HOST}${NC}"
echo ""

# ── Step 1: SSH connectivity ────────────────────────────────────────────────

step 1 "Verifying SSH connectivity"

if ssh -o ConnectTimeout=5 -o BatchMode=yes "$SSH_TARGET" "echo ok" &>/dev/null; then
    ok "SSH to ${SSH_TARGET} works"
else
    fail "Cannot SSH to ${SSH_TARGET}"
    echo "  Check: ssh-copy-id ${SSH_TARGET}"
    exit 1
fi

# Get remote OS info
REMOTE_ARCH=$(ssh "$SSH_TARGET" "uname -m" 2>/dev/null || echo "unknown")
REMOTE_OS=$(ssh "$SSH_TARGET" "uname -s" 2>/dev/null || echo "unknown")
info "Remote: ${REMOTE_OS} ${REMOTE_ARCH}"

# ── Step 2: Check remote prerequisites ──────────────────────────────────────

step 2 "Checking remote prerequisites"

# Check each prerequisite
PREREQS_OK=true

for cmd in git python3 tmux; do
    if ssh "$SSH_TARGET" "command -v $cmd" &>/dev/null; then
        VERSION=$(ssh "$SSH_TARGET" "$cmd --version 2>&1 | head -1" 2>/dev/null || echo "unknown")
        ok "$cmd: $VERSION"
    else
        fail "$cmd not found on remote"
        PREREQS_OK=false
    fi
done

# Check claude CLI
if ssh "$SSH_TARGET" "command -v claude" &>/dev/null; then
    ok "claude CLI found"
else
    warn "claude CLI not found on remote"
    warn "  Agents cannot run without it. Install before launching."
fi

# Check sshfs
if ssh "$SSH_TARGET" "command -v sshfs" &>/dev/null; then
    ok "sshfs available"
else
    warn "sshfs not installed on remote. Attempting install..."
    if ssh "$SSH_TARGET" "sudo apt-get install -y sshfs 2>/dev/null || sudo pacman -S --noconfirm sshfs 2>/dev/null || sudo dnf install -y sshfs 2>/dev/null" &>/dev/null; then
        ok "sshfs installed"
    else
        fail "Could not install sshfs automatically"
        warn "  Install manually: sudo apt-get install sshfs"
        PREREQS_OK=false
    fi
fi

if [[ "$PREREQS_OK" != "true" ]]; then
    fail "Prerequisites check failed. Fix the above issues and re-run."
    exit 1
fi

# ── Step 3: Clone or update repo ────────────────────────────────────────────

step 3 "Cloning/updating soul-team repository"

REMOTE_REPO_DIR="/home/${REMOTE_USER}/soul-team"

CLONE_STATUS=$(ssh "$SSH_TARGET" "
    if [[ -d '${REMOTE_REPO_DIR}/.git' ]]; then
        cd '${REMOTE_REPO_DIR}'
        git fetch --all 2>&1
        git pull --ff-only 2>&1 || echo 'PULL_CONFLICT'
        echo 'UPDATED'
    else
        git clone '${REPO_URL}' '${REMOTE_REPO_DIR}' 2>&1
        echo 'CLONED'
    fi
" 2>&1)

if echo "$CLONE_STATUS" | grep -q "CLONED"; then
    ok "Cloned soul-team to ${REMOTE_REPO_DIR}"
elif echo "$CLONE_STATUS" | grep -q "UPDATED"; then
    ok "Updated existing soul-team repo"
elif echo "$CLONE_STATUS" | grep -q "PULL_CONFLICT"; then
    warn "Repo exists but has local changes. Pull skipped."
    ok "Using existing repo at ${REMOTE_REPO_DIR}"
else
    warn "Git operation output: ${CLONE_STATUS}"
    ok "Repo ready at ${REMOTE_REPO_DIR}"
fi

# ── Step 4: Run setup.sh on remote ──────────────────────────────────────────

step 4 "Running setup.sh on remote"

ssh "$SSH_TARGET" "cd '${REMOTE_REPO_DIR}' && bash setup.sh" 2>&1 | while IFS= read -r line; do
    echo "  ${DIM}[remote]${NC} $line"
done

ok "Remote setup.sh completed"

# ── Step 5: Set up SSHFS mounts for shared communication ────────────────────

step 5 "Configuring SSHFS mounts for shared filesystems"

# Ensure remote SSH key can reach primary
info "Checking reverse SSH (remote -> primary)..."
REVERSE_SSH_OK=$(ssh "$SSH_TARGET" "ssh -o ConnectTimeout=5 -o BatchMode=yes ${PRIMARY_USER}@${PRIMARY_HOST} 'echo ok' 2>/dev/null" || echo "FAIL")

if [[ "$REVERSE_SSH_OK" == *"ok"* ]]; then
    ok "Remote can SSH back to primary (${PRIMARY_HOST})"
else
    warn "Remote cannot SSH back to primary."
    warn "  Setting up SSH key on remote..."

    # Check if remote has an SSH key
    HAS_KEY=$(ssh "$SSH_TARGET" "test -f ~/.ssh/id_ed25519 && echo yes || echo no")
    if [[ "$HAS_KEY" == "no" ]]; then
        info "Generating SSH key on remote..."
        ssh "$SSH_TARGET" "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -q"
        ok "Generated SSH key on remote"
    fi

    # Get the remote's public key and add to primary's authorized_keys
    REMOTE_PUBKEY=$(ssh "$SSH_TARGET" "cat ~/.ssh/id_ed25519.pub")
    if ! grep -qF "$REMOTE_PUBKEY" ~/.ssh/authorized_keys 2>/dev/null; then
        echo "$REMOTE_PUBKEY" >> ~/.ssh/authorized_keys
        ok "Added remote's public key to primary authorized_keys"
    else
        ok "Remote's public key already in primary authorized_keys"
    fi

    # Test again
    REVERSE_SSH_OK=$(ssh "$SSH_TARGET" "ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes ${PRIMARY_USER}@${PRIMARY_HOST} 'echo ok' 2>/dev/null" || echo "FAIL")
    if [[ "$REVERSE_SSH_OK" == *"ok"* ]]; then
        ok "Reverse SSH now works"
    else
        fail "Still cannot establish reverse SSH."
        warn "  Manual fix: on remote, run: ssh-copy-id ${PRIMARY_USER}@${PRIMARY_HOST}"
    fi
fi

# Create mount points on remote
info "Creating mount points on remote..."
ssh "$SSH_TARGET" "
    mkdir -p ~/soul-roles
    mkdir -p ~/.clawteam
    mkdir -p ~/.claude/agents
    mkdir -p ~/.claude/skills
    mkdir -p ~/.claude/scripts
    mkdir -p ~/.claude/agent-memory
    mkdir -p ~/.local/share/assistant
    mkdir -p ~/.soul
    mkdir -p ~/.soul/preflight
    mkdir -p ~/.soul/health
"
ok "Mount points created"

# Generate systemd mount service
info "Generating soul-mounts.service on remote..."

SSHFS_OPTS="reconnect,ServerAliveInterval=15,IdentityFile=/home/${REMOTE_USER}/.ssh/id_ed25519,StrictHostKeyChecking=no"
PRIMARY="${PRIMARY_USER}@${PRIMARY_HOST}"

# Define mount pairs: local_on_primary -> same_on_remote
MOUNT_PAIRS=(
    "soul-roles:soul-roles"
    ".clawteam:.clawteam"
    ".claude/agents:.claude/agents"
    ".claude/skills:.claude/skills"
    ".claude/scripts:.claude/scripts"
    ".claude/agent-memory:.claude/agent-memory"
    ".local/share/assistant:.local/share/assistant"
)

# Build ExecStart command
EXEC_START_PARTS=""
for pair in "${MOUNT_PAIRS[@]}"; do
    SRC="${pair%%:*}"
    DST="${pair##*:}"
    REMOTE_PATH="/home/${REMOTE_USER}/${DST}"
    PRIMARY_PATH="/home/${PRIMARY_USER}/${SRC}"
    EXEC_START_PARTS="${EXEC_START_PARTS}mountpoint -q ${REMOTE_PATH} || sshfs ${PRIMARY}:${PRIMARY_PATH} ${REMOTE_PATH} -o \$OPTS; "
done

# Build ExecStop command
EXEC_STOP_PARTS=""
for pair in "${MOUNT_PAIRS[@]}"; do
    DST="${pair##*:}"
    REMOTE_PATH="/home/${REMOTE_USER}/${DST}"
    EXEC_STOP_PARTS="${EXEC_STOP_PARTS}fusermount -u ${REMOTE_PATH} 2>/dev/null; "
done

SERVICE_CONTENT="[Unit]
Description=Soul team sshfs mounts from ${PRIMARY_HOST} (primary)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${REMOTE_USER}

ExecStart=/bin/bash -c 'OPTS=\"${SSHFS_OPTS}\"; ${EXEC_START_PARTS}'

ExecStop=/bin/bash -c '${EXEC_STOP_PARTS}'

[Install]
WantedBy=multi-user.target"

# Write service file on remote
ssh "$SSH_TARGET" "cat > /tmp/soul-mounts.service << 'SVCEOF'
${SERVICE_CONTENT}
SVCEOF
sudo cp /tmp/soul-mounts.service /etc/systemd/system/soul-mounts.service
sudo systemctl daemon-reload
sudo systemctl enable soul-mounts.service
"
ok "soul-mounts.service installed and enabled"

# Start the mounts
info "Starting SSHFS mounts..."
ssh "$SSH_TARGET" "sudo systemctl start soul-mounts.service" 2>/dev/null || true

# Verify mounts
MOUNT_COUNT=$(ssh "$SSH_TARGET" "mount | grep -c sshfs" 2>/dev/null || echo "0")
ok "${MOUNT_COUNT} SSHFS mount(s) active"

# ── Step 6: Copy config ─────────────────────────────────────────────────────

step 6 "Syncing configuration to remote"

if [[ -f "$CONFIG_FILE" ]]; then
    scp -q "$CONFIG_FILE" "${SSH_TARGET}:/home/${REMOTE_USER}/.soul-team/config.toml"
    ok "Copied config.toml to remote"
else
    warn "No config file found at ${CONFIG_FILE}"
fi

# ── Step 7: Verification ────────────────────────────────────────────────────

step 7 "Verification"

VERIFY_RESULT=$(ssh "$SSH_TARGET" "
    ERRORS=0

    # Check repo
    if [[ -d ~/soul-team/.git ]]; then
        echo 'REPO: ok'
    else
        echo 'REPO: FAIL'
        ERRORS=\$((ERRORS+1))
    fi

    # Check bin symlinks
    if [[ -L ~/.local/bin/soul-team ]]; then
        echo 'BIN: ok'
    else
        echo 'BIN: FAIL'
        ERRORS=\$((ERRORS+1))
    fi

    # Check config
    if [[ -f ~/.soul-team/config.toml ]]; then
        echo 'CONFIG: ok'
    else
        echo 'CONFIG: FAIL'
        ERRORS=\$((ERRORS+1))
    fi

    # Check mounts
    MOUNTS=\$(mount | grep sshfs | wc -l)
    if [[ \$MOUNTS -gt 0 ]]; then
        echo \"MOUNTS: ok (\${MOUNTS} active)\"
    else
        echo 'MOUNTS: FAIL (0 active)'
        ERRORS=\$((ERRORS+1))
    fi

    # Check comms directories accessible
    if [[ -d ~/.clawteam/teams ]]; then
        echo 'COMMS: ok'
    else
        echo 'COMMS: FAIL'
        ERRORS=\$((ERRORS+1))
    fi

    # Check agent personas accessible
    if [[ -d ~/.claude/agents ]]; then
        PERSONA_COUNT=\$(ls ~/.claude/agents/*.md 2>/dev/null | wc -l)
        echo \"PERSONAS: ok (\${PERSONA_COUNT} files)\"
    else
        echo 'PERSONAS: FAIL'
        ERRORS=\$((ERRORS+1))
    fi

    # Check claude CLI
    if command -v claude &>/dev/null; then
        echo 'CLAUDE: ok'
    else
        echo 'CLAUDE: missing'
    fi

    echo \"TOTAL_ERRORS: \${ERRORS}\"
" 2>&1)

echo ""
info "Verification results:"
echo "$VERIFY_RESULT" | while IFS= read -r line; do
    if echo "$line" | grep -q "FAIL"; then
        fail "$line"
    elif echo "$line" | grep -q "ok"; then
        ok "$line"
    elif echo "$line" | grep -q "missing"; then
        warn "$line"
    fi
done

TOTAL_ERRORS=$(echo "$VERIFY_RESULT" | grep "TOTAL_ERRORS" | awk '{print $2}')

echo ""
echo "=========================================="
if [[ "${TOTAL_ERRORS:-0}" == "0" ]]; then
    echo -e "${GREEN}  Remote setup complete!${NC}"
    echo ""
    echo "  The remote machine is ready to run agents."
    echo "  Mounts will auto-start on boot via soul-mounts.service."
    echo ""
    echo "  To test manually:"
    echo "    ssh ${SSH_TARGET} 'systemctl status soul-mounts.service'"
    echo "    ssh ${SSH_TARGET} 'ls ~/.clawteam/teams/'"
else
    echo -e "${YELLOW}  Remote setup completed with ${TOTAL_ERRORS} warning(s).${NC}"
    echo "  Review the failures above and re-run if needed."
fi
echo ""
