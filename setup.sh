#!/usr/bin/env bash
# soul-team setup — clone-and-go installer
# Safe to re-run (idempotent).
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  [ok] $*${NC}"; }
warn() { echo -e "${YELLOW}  [!!] $*${NC}"; }
fail() { echo -e "${RED}  [FAIL] $*${NC}"; exit 1; }
info() { echo -e "  ${BOLD}$*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BOLD}soul-team installer${NC}"
echo "=========================================="
echo ""

# ── 1. Check prerequisites ──────────────────────────────────────────────────

info "Checking prerequisites..."

# tmux >= 3.2
if command -v tmux &>/dev/null; then
    TMUX_VER=$(tmux -V | awk '{print $2}')
    TMUX_MAJOR=$(echo "$TMUX_VER" | cut -d. -f1)
    TMUX_MINOR=$(echo "$TMUX_VER" | cut -d. -f2 | tr -dc '0-9')
    if [[ "$TMUX_MAJOR" -gt 3 ]] || [[ "$TMUX_MAJOR" -eq 3 && "$TMUX_MINOR" -ge 2 ]]; then
        ok "tmux $TMUX_VER"
    else
        warn "tmux $TMUX_VER found -- soul-team requires >= 3.2. Some features may not work."
    fi
else
    fail "tmux not found. Install tmux >= 3.2 and re-run."
fi

# python3 >= 3.11
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        ok "Python $PY_VER"
    else
        warn "Python $PY_VER found -- soul-team requires >= 3.11. Some features may not work."
    fi
else
    fail "python3 not found. Install Python >= 3.11 and re-run."
fi

# claude CLI
if command -v claude &>/dev/null; then
    ok "claude CLI ($(claude --version 2>/dev/null | head -1 || echo 'found'))"
else
    warn "claude not found. Install Claude Code CLI before running soul-team."
fi

# clawteam
if command -v clawteam &>/dev/null; then
    ok "clawteam CLI"
else
    warn "clawteam not found. Message bus features will be unavailable."
    warn "  -> See: https://github.com/clawteam/clawteam"
fi

# jq (optional)
if command -v jq &>/dev/null; then
    ok "jq (optional) found"
else
    warn "jq not found -- optional, used for panes.json manipulation."
fi

echo ""

# ── 2. Install Python dependencies ──────────────────────────────────────────

info "Installing Python dependencies..."

DEPS="watchdog psutil"
if python3 -m pip install --user $DEPS --quiet 2>/dev/null; then
    ok "$DEPS installed"
else
    warn "pip install failed -- trying without --user flag"
    if python3 -m pip install $DEPS --quiet 2>/dev/null; then
        ok "$DEPS installed (system)"
    else
        warn "Could not install $DEPS. Install manually: pip3 install $DEPS"
    fi
fi

echo ""

# ── 3. Symlink bin/* to ~/.local/bin/ ────────────────────────────────────────

info "Symlinking bin scripts -> ~/.local/bin/"

BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"

for script in "$SCRIPT_DIR"/bin/*; do
    BASENAME=$(basename "$script")
    DEST="${BIN_DIR}/${BASENAME}"
    if [[ -L "$DEST" ]]; then
        rm "$DEST"
    fi
    ln -sf "$script" "$DEST"
    ok "$BASENAME -> $DEST"
done

# Ensure ~/.local/bin is on PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    warn "${BIN_DIR} is not in your PATH."
    warn "  Add this to your ~/.bashrc or ~/.zshrc:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""

# ── 4. Copy systemd units to ~/.config/systemd/user/ ────────────────────────

info "Installing systemd services..."

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    mkdir -p "$SYSTEMD_USER_DIR"
    INSTALLED_SERVICES=0

    for svc_file in "$SCRIPT_DIR"/systemd/*.service; do
        [ -f "$svc_file" ] || continue
        SVC_NAME=$(basename "$svc_file")
        cp "$svc_file" "${SYSTEMD_USER_DIR}/${SVC_NAME}"
        ok "${SVC_NAME} installed"
        INSTALLED_SERVICES=$((INSTALLED_SERVICES + 1))
    done

    if [[ "$INSTALLED_SERVICES" -gt 0 ]]; then
        systemctl --user daemon-reload
        ok "systemd daemon-reload done"
        warn "Services installed but NOT enabled by default."
        warn "  To enable:  systemctl --user enable --now soul-courier soul-guardian soul-router"
    fi
else
    warn "systemd user session not available -- skipping service installation"
    warn "  Daemons can be started manually via the soul-team CLI."
fi

echo ""

# ── 5. Create runtime directories ───────────────────────────────────────────

info "Creating runtime directories..."

RUNTIME_DIRS=(
    "${HOME}/.soul"
    "${HOME}/.soul/preflight"
    "${HOME}/.soul/health"
    "${HOME}/.clawteam/teams/soul-team"
    "${HOME}/.clawteam/teams/soul-team/inboxes"
    "${HOME}/.clawteam/teams/soul-team/broadcast"
    "${HOME}/.clawteam/teams/soul-team/discussions"
    "${HOME}/.clawteam/teams/soul-team/sidecar"
    "${HOME}/.claude/config"
    "${HOME}/.claude/logs"
)

for dir in "${RUNTIME_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        ok "$dir (exists)"
    else
        mkdir -p "$dir"
        ok "$dir (created)"
    fi
done

echo ""

# ── 6. Copy config example if no config exists ──────────────────────────────

info "Installing configuration..."

CONFIG_DEST="${HOME}/.claude/config/soul-team.toml"
CONFIG_EXAMPLE="${SCRIPT_DIR}/config/soul-team.toml.example"
NEEDS_INIT=false

if [[ -f "$CONFIG_DEST" ]]; then
    ok "soul-team.toml already exists -- skipping (will not overwrite)"
else
    NEEDS_INIT=true
    if [[ -f "$CONFIG_EXAMPLE" ]]; then
        cp "$CONFIG_EXAMPLE" "$CONFIG_DEST"
        ok "soul-team.toml installed -> $CONFIG_DEST"
        warn "This is a template config. Run 'soul-team init' to customize."
    else
        warn "config/soul-team.toml.example not found -- skipping"
        warn "Run 'soul-team init' to generate your config interactively."
    fi
fi

echo ""

# ── 7. Print success summary ────────────────────────────────────────────────

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  soul-team installed successfully!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "  Next steps:"
echo ""
if $NEEDS_INIT; then
    echo -e "  1. ${BOLD}Configure your team:${NC}"
    echo -e "     ${BOLD}soul-team init${NC}          # Interactive setup wizard"
    echo -e "     ${BOLD}soul-team init --quick${NC}   # Quick start (3 agents, no prompts)"
    echo ""
    echo -e "  2. Start your agent team:"
    echo -e "     ${BOLD}soul-team${NC}"
else
    echo -e "  1. Start your agent team:"
    echo -e "     ${BOLD}soul-team${NC}"
fi
echo ""
echo -e "  Send a message to an agent:"
echo -e "     ${BOLD}soul-msg send <agent-name> \"Hello from the terminal\"${NC}"
echo ""
echo -e "  Check team health:"
echo -e "     ${BOLD}soul-health${NC}"
echo ""
echo -e "  Optional -- run daemons with systemd:"
echo -e "     ${BOLD}systemctl --user enable --now soul-courier soul-guardian soul-router${NC}"
echo ""
echo -e "  Docs: https://github.com/rishav1305/soul-team"
echo ""
