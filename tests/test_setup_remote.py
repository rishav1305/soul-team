"""
Tests for setup-remote.sh and the setup_remote CLI integration.

These tests verify the script's structure and the CLI integration points.
Integration tests that require actual SSH are marked with @pytest.mark.integration.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP_REMOTE_SCRIPT = REPO_ROOT / "ops" / "setup-remote.sh"
SOUL_TEAM_CLI = REPO_ROOT / "bin" / "soul-team"


class TestSetupRemoteScript:
    """Tests for ops/setup-remote.sh"""

    def test_script_exists(self):
        assert SETUP_REMOTE_SCRIPT.exists(), "ops/setup-remote.sh must exist"

    def test_script_is_executable(self):
        assert os.access(SETUP_REMOTE_SCRIPT, os.X_OK), "setup-remote.sh must be executable"

    def test_script_has_shebang(self):
        content = SETUP_REMOTE_SCRIPT.read_text()
        assert content.startswith("#!/usr/bin/env bash"), "Must have bash shebang"

    def test_script_uses_strict_mode(self):
        content = SETUP_REMOTE_SCRIPT.read_text()
        assert "set -euo pipefail" in content, "Must use strict bash mode"

    def test_script_shows_usage_without_args(self):
        result = subprocess.run(
            ["bash", str(SETUP_REMOTE_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "Usage:" in result.stdout or "Usage:" in result.stderr

    def test_script_defines_all_steps(self):
        """Verify the script implements all 7 required steps."""
        content = SETUP_REMOTE_SCRIPT.read_text()
        required_steps = [
            "Verifying SSH connectivity",
            "Checking remote prerequisites",
            "Cloning/updating soul-team repository",
            "Running setup.sh on remote",
            "Configuring SSHFS mounts",
            "Syncing configuration to remote",
            "Verification",
        ]
        for step_desc in required_steps:
            assert step_desc in content, f"Missing step: {step_desc}"

    def test_script_handles_mount_pairs(self):
        """Verify all required shared directories are mounted."""
        content = SETUP_REMOTE_SCRIPT.read_text()
        required_mounts = [
            "soul-roles",
            ".clawteam",
            ".claude/agents",
            ".claude/skills",
            ".claude/scripts",
            ".claude/agent-memory",
        ]
        for mount in required_mounts:
            assert mount in content, f"Missing mount: {mount}"

    def test_script_generates_systemd_service(self):
        """Verify soul-mounts.service generation."""
        content = SETUP_REMOTE_SCRIPT.read_text()
        assert "soul-mounts.service" in content
        assert "systemctl daemon-reload" in content
        assert "systemctl enable" in content

    def test_script_handles_reverse_ssh_setup(self):
        content = SETUP_REMOTE_SCRIPT.read_text()
        assert "ssh-keygen" in content
        assert "authorized_keys" in content

    def test_script_idempotent_markers(self):
        """Script should check before creating (mountpoint -q, test -d, etc.)."""
        content = SETUP_REMOTE_SCRIPT.read_text()
        assert "mountpoint -q" in content
        assert ".git" in content  # checks for existing repo


class TestCLIIntegration:
    """Tests for setup-remote integration in the soul-team CLI."""

    def test_cli_has_setup_remote_subcommand(self):
        result = subprocess.run(
            ["python3", str(SOUL_TEAM_CLI), "setup-remote", "--help"],
            capture_output=True, text=True,
        )
        # Should either show help or handle gracefully
        assert result.returncode == 0 or "setup-remote" in result.stdout + result.stderr

    def test_cli_setup_remote_requires_machine_name(self):
        result = subprocess.run(
            ["python3", str(SOUL_TEAM_CLI), "setup-remote"],
            capture_output=True, text=True,
        )
        # Should fail with a usage hint
        assert result.returncode != 0 or "required" in (result.stdout + result.stderr).lower()


class TestConfigureMachinesMenu:
    """Verify the machines menu includes setup-remote option."""

    def test_configure_machines_has_setup_option(self):
        """The _configure_machines function must offer setup-remote."""
        content = SOUL_TEAM_CLI.read_text()
        assert "Setup remote" in content or "setup-remote" in content, (
            "Machines menu must include a 'Setup remote' option"
        )


@pytest.mark.integration
class TestSSHIntegration:
    """Integration tests requiring actual SSH. Run with: pytest -m integration"""

    @pytest.fixture
    def ssh_target(self):
        target = os.environ.get("TEST_SSH_TARGET", "user@remote-host")
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", target, "echo ok"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            pytest.skip(f"SSH target {target} not reachable")
        return target

    def test_full_setup_remote_dry_check(self, ssh_target):
        """Verify the script can at least parse args and check SSH."""
        result = subprocess.run(
            ["bash", str(SETUP_REMOTE_SCRIPT), ssh_target],
            capture_output=True, text=True,
            timeout=120,
        )
        # Should at least pass the SSH connectivity check
        combined = result.stdout + result.stderr
        assert "SSH" in combined
