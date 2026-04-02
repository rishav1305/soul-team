#!/usr/bin/env bash
# soul-team — one-line installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/rishav1305/soul-team/main/install.sh | bash
#   curl -fsSL http://git.titan.local:3000/admin/soul-team/raw/branch/main/install.sh | bash
#
# Options (via env vars):
#   SOUL_DIR=~/my-team    — install location (default: ~/soul-team)
#   SOUL_REMOTE=gitea     — clone from gitea instead of github (default: github)
#   SOUL_BRANCH=dev       — branch to clone (default: main)
#
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  [ok] $*${NC}"; }
fail() { echo -e "${RED}  [FAIL] $*${NC}"; exit 1; }

INSTALL_DIR="${SOUL_DIR:-$HOME/soul-team}"
BRANCH="${SOUL_BRANCH:-main}"
REMOTE="${SOUL_REMOTE:-github}"

# Remote URLs
GITHUB_URL="https://github.com/rishav1305/soul-team.git"
GITEA_URL="ssh://git@git.titan.local:222/admin/soul-team.git"

echo ""
echo -e "${BOLD}soul-team installer${NC}"
echo "=========================================="
echo ""

# ── 1. Check prerequisites ──────────────────────────────────
command -v git  &>/dev/null || fail "git not found. Install git and re-run."
command -v tmux &>/dev/null || fail "tmux not found. Install tmux >= 3.2 and re-run."
command -v python3 &>/dev/null || fail "python3 not found. Install Python >= 3.11 and re-run."

PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [[ "$PY_MINOR" -lt 11 ]]; then
    fail "Python 3.11+ required (found 3.$PY_MINOR)"
fi
ok "Prerequisites: git, tmux, python3"

# ── 2. Clone or update ──────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Existing install found at $INSTALL_DIR — pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH" 2>/dev/null || {
        echo "  Pull failed — continuing with existing version."
    }
    ok "Updated $INSTALL_DIR"
else
    if [[ "$REMOTE" == "gitea" ]]; then
        CLONE_URL="$GITEA_URL"
    else
        CLONE_URL="$GITHUB_URL"
    fi
    echo "  Cloning from $CLONE_URL..."
    git clone --branch "$BRANCH" --depth 1 "$CLONE_URL" "$INSTALL_DIR" || fail "Clone failed"
    ok "Cloned to $INSTALL_DIR"
fi

# ── 3. Run setup ────────────────────────────────────────────
echo ""
if [[ -x "$INSTALL_DIR/setup.sh" ]]; then
    bash "$INSTALL_DIR/setup.sh"
else
    fail "setup.sh not found or not executable in $INSTALL_DIR"
fi

# ── 4. Offer interactive setup ──────────────────────────────
echo ""
# Create user config directory
mkdir -p "$HOME/.soul-team"

# Check both new and legacy config locations
CONFIG_FILE="$HOME/.soul-team/config.toml"
LEGACY_CONFIG="$HOME/.claude/config/soul-team.toml"

if [[ ! -f "$CONFIG_FILE" ]] && [[ ! -f "$LEGACY_CONFIG" ]]; then
    echo -e "  ${BOLD}No team configuration found.${NC}"
    echo ""
    echo "  Run 'soul-team' to start the interactive setup."
    echo ""
fi

# ── 5. Done ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=========================================="
echo -e "  soul-team is ready!"
echo -e "==========================================${NC}"
echo ""
echo "  Get started:"
echo ""
echo -e "  ${BOLD}soul-team${NC}               # Interactive setup + launch (one command)"
echo ""
echo "  To update later:"
echo -e "  ${BOLD}cd $INSTALL_DIR && git pull && ./setup.sh${NC}"
echo ""
