#!/usr/bin/env bash
# soul-team setup — install soul-team on this machine
# Safe to re-run (idempotent).
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; exit 1; }
info() { echo -e "  ${BOLD}$*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BOLD}soul-team installer${NC}"
echo "────────────────────────────────────────"
echo ""

# ── 1. Check prerequisites ────────────────────────────────────────────────────

info "Checking prerequisites…"

# tmux ≥ 3.2
if command -v tmux &>/dev/null; then
    TMUX_VER=$(tmux -V | awk '{print $2}')
    TMUX_MAJOR=$(echo "$TMUX_VER" | cut -d. -f1)
    TMUX_MINOR=$(echo "$TMUX_VER" | cut -d. -f2 | tr -dc '0-9')
    if [[ "$TMUX_MAJOR" -gt 3 ]] || [[ "$TMUX_MAJOR" -eq 3 && "$TMUX_MINOR" -ge 2 ]]; then
        ok "tmux $TMUX_VER"
    else
        warn "tmux $TMUX_VER found — soul-team requires ≥ 3.2. Some features may not work."
    fi
else
    fail "tmux not found. Install tmux ≥ 3.2 and re-run."
fi

# python3 ≥ 3.11
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        ok "Python $PY_VER"
    else
        warn "Python $PY_VER found — soul-team requires ≥ 3.11. Some features may not work."
    fi
else
    fail "python3 not found. Install Python ≥ 3.11 and re-run."
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
    warn "  → See: https://github.com/clawteam/clawteam"
fi

# jq (optional)
if command -v jq &>/dev/null; then
    ok "jq (optional) found"
else
    warn "jq not found — optional, used for panes.json manipulation."
fi

echo ""

# ── 2. Create directories ─────────────────────────────────────────────────────

info "Creating directories…"

CONFIG_DIR="${HOME}/.config/soul-team"
DATA_DIR="${HOME}/.local/share/soul-team"
LOG_DIR="${DATA_DIR}/logs"
TEAM_DIR="${DATA_DIR}/teams/soul-team"
BIN_DIR="${HOME}/.local/bin"

for dir in "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$TEAM_DIR" "$BIN_DIR"; do
    if [[ -d "$dir" ]]; then
        ok "$dir (exists)"
    else
        mkdir -p "$dir"
        ok "$dir (created)"
    fi
done

echo ""

# ── 3. Copy cluster.yaml.example ─────────────────────────────────────────────

info "Installing configuration…"

CLUSTER_EXAMPLE="${SCRIPT_DIR}/cluster.yaml.example"
CLUSTER_DEST="${CONFIG_DIR}/cluster.yaml"

if [[ -f "$CLUSTER_DEST" ]]; then
    warn "cluster.yaml already exists — skipping (will not overwrite)"
else
    if [[ -f "$CLUSTER_EXAMPLE" ]]; then
        cp "$CLUSTER_EXAMPLE" "$CLUSTER_DEST"
        ok "cluster.yaml installed → $CLUSTER_DEST"
    else
        warn "cluster.yaml.example not found in $SCRIPT_DIR — skipping"
    fi
fi

echo ""

# ── 4. Install Python dependencies ───────────────────────────────────────────

info "Installing Python dependencies…"

if python3 -m pip install --user PyYAML psutil --quiet; then
    ok "PyYAML, psutil installed"
else
    fail "pip install failed. Try: python3 -m pip install --user PyYAML psutil"
fi

echo ""

# ── 5. Install bin scripts ────────────────────────────────────────────────────

info "Installing bin scripts → $BIN_DIR"

for script in soul-team soul-msg; do
    SRC="${SCRIPT_DIR}/bin/${script}"
    DEST="${BIN_DIR}/${script}"
    if [[ -f "$SRC" ]]; then
        cp "$SRC" "$DEST"
        chmod +x "$DEST"
        ok "$script"
    else
        warn "bin/${script} not found in $SCRIPT_DIR — skipping"
    fi
done

# Ensure ~/.local/bin is on PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    warn "${BIN_DIR} is not in your PATH."
    warn "  Add this to your ~/.bashrc or ~/.zshrc:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""

# ── 6. Install Python packages (courier / guardian) ───────────────────────────

info "Installing daemon packages → $DATA_DIR"

for pkg in courier guardian; do
    SRC="${SCRIPT_DIR}/${pkg}"
    DEST="${DATA_DIR}/${pkg}"
    if [[ -d "$SRC" ]]; then
        cp -r "$SRC" "$DEST"
        ok "${pkg}/ copied"
    elif [[ -f "${SCRIPT_DIR}/${pkg}.py" ]]; then
        cp "${SCRIPT_DIR}/${pkg}.py" "${DATA_DIR}/${pkg}.py"
        ok "${pkg}.py copied"
    else
        warn "${pkg} not found in $SCRIPT_DIR — skipping"
    fi
done

# Copy MCP server if present
if [[ -d "${SCRIPT_DIR}/mcp-server" ]]; then
    cp -r "${SCRIPT_DIR}/mcp-server" "${DATA_DIR}/mcp-server"
    ok "mcp-server/ copied"
fi

echo ""

# ── 7. Optionally install systemd services ────────────────────────────────────

info "Checking for systemd…"

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    mkdir -p "$SYSTEMD_USER_DIR"
    INSTALLED_SERVICES=0

    for svc in soul-courier soul-guardian; do
        SVC_SRC="${SCRIPT_DIR}/systemd/${svc}.service"
        SVC_DEST="${SYSTEMD_USER_DIR}/${svc}.service"
        if [[ -f "$SVC_SRC" ]]; then
            cp "$SVC_SRC" "$SVC_DEST"
            ok "${svc}.service installed"
            INSTALLED_SERVICES=$((INSTALLED_SERVICES + 1))
        else
            warn "systemd/${svc}.service not found — skipping"
        fi
    done

    if [[ "$INSTALLED_SERVICES" -gt 0 ]]; then
        systemctl --user daemon-reload
        ok "systemd daemon-reload done"
        warn "Services are installed but NOT enabled by default."
        warn "  To enable:  systemctl --user enable --now soul-courier soul-guardian"
    fi
else
    warn "systemd user session not available — skipping service installation"
    warn "  Daemons can be started manually via the soul-team CLI."
fi

echo ""

# ── 8. Print success summary ──────────────────────────────────────────────────

echo -e "${GREEN}────────────────────────────────────────${NC}"
echo -e "${GREEN}  soul-team installed successfully!${NC}"
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo ""
echo "  Next steps:"
echo ""
echo -e "  1. Edit your cluster config:"
echo -e "     ${BOLD}${CONFIG_DIR}/cluster.yaml${NC}"
echo ""
echo -e "  2. Start your agent team:"
echo -e "     ${BOLD}soul-team${NC}"
echo ""
echo -e "  3. Send a message to an agent:"
echo -e "     ${BOLD}soul-msg <agent-name> \"Hello from the terminal\"${NC}"
echo ""
echo -e "  4. Optional — run daemons with systemd:"
echo -e "     ${BOLD}systemctl --user enable --now soul-courier soul-guardian${NC}"
echo ""
echo -e "  Docs: https://github.com/your-org/soul-team"
echo ""
