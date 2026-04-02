"""
test_soul_msg.py -- Tests for soul-msg CLI

Covers:
  1. cmd_send — validates args, dispatches to clawteam, writes to correct inbox
  2. cmd_broadcast — writes to broadcast dir via clawteam
  3. cmd_inbox / cmd_peek — reads agent pane
  4. Agent name validation & priority tags
  5. Helper functions (priority_tag, append_native_inbox, run_clawteam)
  6. Argument parsing

Run:
    cd ~/.claude/scripts && python3 -m pytest tests/test_soul_msg.py -v --timeout=10
"""

import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from argparse import Namespace

import pytest

# ---------------------------------------------------------------------------
# Setup: import the soul-msg module
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

# soul-msg has no .py extension — use importlib.util with explicit loader
import importlib.util
import importlib.machinery
_soul_msg_path = str(SCRIPTS_DIR / "soul-msg")
_loader = importlib.machinery.SourceFileLoader("soul_msg", _soul_msg_path)
_spec = importlib.util.spec_from_file_location("soul_msg", _soul_msg_path, loader=_loader)
soul_msg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(soul_msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_inbox(tmp_path):
    """Create a temporary native inbox directory."""
    inbox_dir = tmp_path / "inboxes"
    inbox_dir.mkdir()
    inbox_file = inbox_dir / "team-lead.json"
    inbox_file.write_text("[]")
    return inbox_dir, inbox_file


# ===========================================================================
# 1. Constants & Agent List
# ===========================================================================

class TestConstants:
    """Tests for module constants."""

    def test_agents_list(self):
        """AGENTS contains all expected agent names."""
        expected = {"happy", "shuri", "loki", "fury",
                    "xavier", "hawkeye", "stark", "banner", "pepper"}
        assert set(soul_msg.AGENTS) == expected

    def test_agents_count(self):
        """AGENTS has 9 entries."""
        assert len(soul_msg.AGENTS) == 9

    def test_team_constant(self):
        """TEAM is soul-team."""
        assert soul_msg.TEAM == "soul-team"


# ===========================================================================
# 2. priority_tag
# ===========================================================================

class TestPriorityTag:
    """Tests for priority_tag() conversion."""

    def test_p1_to_urgent(self):
        assert soul_msg.priority_tag("P1") == "urgent"

    def test_p2_to_normal(self):
        assert soul_msg.priority_tag("P2") == "normal"

    def test_p3_to_low(self):
        assert soul_msg.priority_tag("P3") == "low"

    def test_unknown_defaults_normal(self):
        assert soul_msg.priority_tag("P99") == "normal"

    def test_none_defaults_normal(self):
        assert soul_msg.priority_tag(None) == "normal"


# ===========================================================================
# 3. append_native_inbox
# ===========================================================================

class TestAppendNativeInbox:
    """Tests for append_native_inbox()."""

    def test_append_creates_entry(self, tmp_inbox):
        """append_native_inbox adds a message to the inbox JSON."""
        inbox_dir, inbox_file = tmp_inbox
        with patch.object(soul_msg, "NATIVE_INBOX_DIR", inbox_dir), \
             patch.object(soul_msg, "NATIVE_INBOX_LEAD", inbox_file):
            soul_msg.append_native_inbox("happy", "Test message")

        msgs = json.loads(inbox_file.read_text())
        assert len(msgs) == 1
        assert msgs[0]["from"] == "happy"
        assert msgs[0]["text"] == "Test message"
        assert msgs[0]["read"] is False
        assert "timestamp" in msgs[0]

    def test_append_preserves_existing(self, tmp_inbox):
        """append_native_inbox preserves existing messages."""
        inbox_dir, inbox_file = tmp_inbox
        existing = [{"from": "shuri", "text": "Old msg", "timestamp": "t", "read": True}]
        inbox_file.write_text(json.dumps(existing))

        with patch.object(soul_msg, "NATIVE_INBOX_DIR", inbox_dir), \
             patch.object(soul_msg, "NATIVE_INBOX_LEAD", inbox_file):
            soul_msg.append_native_inbox("fury", "New msg")

        msgs = json.loads(inbox_file.read_text())
        assert len(msgs) == 2
        assert msgs[0]["from"] == "shuri"
        assert msgs[1]["from"] == "fury"

    def test_append_handles_corrupt_file(self, tmp_inbox):
        """append_native_inbox handles corrupt JSON gracefully."""
        inbox_dir, inbox_file = tmp_inbox
        inbox_file.write_text("NOT JSON {{{")

        with patch.object(soul_msg, "NATIVE_INBOX_DIR", inbox_dir), \
             patch.object(soul_msg, "NATIVE_INBOX_LEAD", inbox_file):
            soul_msg.append_native_inbox("loki", "Recovery msg")

        msgs = json.loads(inbox_file.read_text())
        assert len(msgs) == 1
        assert msgs[0]["from"] == "loki"


# ===========================================================================
# 4. cmd_send
# ===========================================================================

class TestCmdSend:
    """Tests for cmd_send() message sending."""

    def test_send_calls_clawteam(self):
        """cmd_send invokes clawteam inbox send with correct args."""
        args = Namespace(recipient="happy", message="Hello", priority="P2")
        with patch.object(soul_msg, "run_clawteam", return_value=(0, "Sent", "")) as mock_ct:
            soul_msg.cmd_send(args)

        mock_ct.assert_called_once()
        call_args = mock_ct.call_args[0]
        assert "inbox" in call_args
        assert "send" in call_args
        assert "happy" in call_args
        assert "Hello" in call_args

    def test_send_mirrors_to_team_lead(self, tmp_inbox):
        """cmd_send mirrors message when recipient is team-lead."""
        inbox_dir, inbox_file = tmp_inbox
        args = Namespace(recipient="team-lead", message="Hey boss", priority="P1")
        with patch.object(soul_msg, "run_clawteam", return_value=(0, "OK", "")), \
             patch.object(soul_msg, "NATIVE_INBOX_DIR", inbox_dir), \
             patch.object(soul_msg, "NATIVE_INBOX_LEAD", inbox_file):
            soul_msg.cmd_send(args)

        msgs = json.loads(inbox_file.read_text())
        assert len(msgs) == 1

    def test_send_exits_on_error(self):
        """cmd_send exits with error code when clawteam fails."""
        args = Namespace(recipient="happy", message="Test", priority="P2")
        with patch.object(soul_msg, "run_clawteam", return_value=(1, "", "Connection refused")):
            with pytest.raises(SystemExit) as exc_info:
                soul_msg.cmd_send(args)
            assert exc_info.value.code == 1


# ===========================================================================
# 5. cmd_broadcast
# ===========================================================================

class TestCmdBroadcast:
    """Tests for cmd_broadcast()."""

    def test_broadcast_calls_clawteam(self):
        """cmd_broadcast invokes clawteam inbox broadcast."""
        args = Namespace(message="All agents report")
        with patch.object(soul_msg, "run_clawteam", return_value=(0, "Broadcast sent", "")) as mock_ct:
            soul_msg.cmd_broadcast(args)

        mock_ct.assert_called_once()
        call_args = mock_ct.call_args[0]
        assert "inbox" in call_args
        assert "broadcast" in call_args

    def test_broadcast_exits_on_error(self):
        """cmd_broadcast exits with error code on failure."""
        args = Namespace(message="Test broadcast")
        with patch.object(soul_msg, "run_clawteam", return_value=(1, "", "Error")):
            with pytest.raises(SystemExit) as exc_info:
                soul_msg.cmd_broadcast(args)
            assert exc_info.value.code == 1


# ===========================================================================
# 6. cmd_peek
# ===========================================================================

class TestCmdPeek:
    """Tests for cmd_peek() tmux pane capture."""

    def test_peek_no_pane(self, tmp_path, capsys):
        """cmd_peek reports when no pane is registered."""
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"members": []}))
        args = Namespace(agent="nonexistent", lines=30)
        with patch("os.path.expanduser", return_value=str(config)):
            # Re-construct the path the function uses
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "read_text", return_value='{"members": []}'):
                soul_msg.cmd_peek(args)

        captured = capsys.readouterr()
        assert "No active tmux pane" in captured.out

    def test_peek_successful_capture(self, tmp_path, capsys):
        """cmd_peek shows pane content when available."""
        config_data = {
            "members": [{"name": "happy", "tmuxPaneId": "%5"}]
        }
        args = Namespace(agent="happy", lines=30)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Agent is working on tasks...\n"

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))

        with patch("os.path.expanduser", return_value=str(config_path)), \
             patch("subprocess.run", return_value=mock_result):
            soul_msg.cmd_peek(args)

        captured = capsys.readouterr()
        assert "happy" in captured.out
        assert "Agent is working" in captured.out


# ===========================================================================
# 7. _print_inbox
# ===========================================================================

class TestPrintInbox:
    """Tests for _print_inbox() display logic."""

    def test_empty_inbox(self, capsys):
        """_print_inbox prints empty message when no messages."""
        args = Namespace(from_agent=None, unread=False)
        soul_msg._print_inbox([], args)
        captured = capsys.readouterr()
        assert "Inbox empty" in captured.out

    def test_filter_by_from_agent(self, capsys):
        """_print_inbox filters messages by from_agent."""
        msgs = [
            {"from": "happy", "text": "Hello", "key": "normal"},
            {"from": "shuri", "text": "Code review", "key": "urgent"},
        ]
        args = Namespace(from_agent="happy", unread=False)
        soul_msg._print_inbox(msgs, args)
        captured = capsys.readouterr()
        assert "happy" in captured.out
        assert "Code review" not in captured.out

    def test_filter_unread(self, capsys):
        """_print_inbox filters to unread messages when --unread set."""
        msgs = [
            {"from": "happy", "text": "Unread", "read": False, "key": "normal"},
            {"from": "shuri", "text": "Read", "read": True, "key": "normal"},
        ]
        args = Namespace(from_agent=None, unread=True)
        soul_msg._print_inbox(msgs, args)
        captured = capsys.readouterr()
        assert "Unread" in captured.out
        # The read message should be filtered out
        lines = captured.out.strip().split("\n")
        # Header + separator + 1 message = 3 lines
        assert len(lines) == 3


# ===========================================================================
# 8. run_clawteam
# ===========================================================================

class TestRunClawteam:
    """Tests for run_clawteam() subprocess wrapper."""

    def test_returns_tuple(self):
        """run_clawteam returns (returncode, stdout, stderr)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            rc, out, err = soul_msg.run_clawteam("test", "cmd")
        assert rc == 0
        assert out == "output"
        assert err == ""


# ===========================================================================
# 9. Argument Parsing
# ===========================================================================

class TestArgParsing:
    """Tests for main() argument parsing structure."""

    def test_send_subcommand_exists(self):
        """Parser accepts 'send' subcommand."""
        # We test by constructing the parser and parsing args
        import argparse
        # Just verify the module's main can parse basic args
        with patch("sys.argv", ["soul-msg", "send", "happy", "Hello"]):
            with patch.object(soul_msg, "cmd_send") as mock:
                soul_msg.main()
            mock.assert_called_once()

    def test_broadcast_subcommand_exists(self):
        """Parser accepts 'broadcast' subcommand."""
        with patch("sys.argv", ["soul-msg", "broadcast", "All report"]):
            with patch.object(soul_msg, "cmd_broadcast") as mock:
                soul_msg.main()
            mock.assert_called_once()

    def test_status_subcommand_exists(self):
        """Parser accepts 'status' subcommand."""
        with patch("sys.argv", ["soul-msg", "status"]):
            with patch.object(soul_msg, "cmd_status") as mock:
                soul_msg.main()
            mock.assert_called_once()
