"""
STQA Phase A — Tests for mcp-server/server.py tool functions.

Design rationale (per Shuri arch review, 2026-04-07):
  FastMCP uses stdio transport — not ASGI/HTTP. The httpx.AsyncClient approach
  in the original SPEC does not apply. Instead we test the tool implementations
  directly: import tool functions, mock run_clawteam() subprocess calls, and
  verify the logic in soul_send_message, soul_check_inbox, soul_broadcast, etc.

  This approach tests our business logic. The MCP protocol layer (FastMCP) is
  tested by the mcp library itself — not our responsibility.

NOTE: create_app() factory (STQA ST-PRE-01) is pending Forge delivery.
  TestMCPCreateApp below is skipped until Forge merges the refactor.

Run: pytest tests/test_mcp_server.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Module setup ──────────────────────────────────────────────────────────────
# mcp-server uses FastMCP (not installed system-wide). Mock the mcp package
# before importing server to avoid ModuleNotFoundError.

_MCP_SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp-server"


def _load_server():
    """Import mcp-server/server.py with mcp package mocked."""
    mock_mcp_pkg = MagicMock()
    mock_fastmcp = MagicMock()

    # FastMCP() returns itself; decorators are pass-through
    def _tool_decorator():
        def _wrap(fn):
            return fn
        return _wrap

    mock_fastmcp_instance = MagicMock()
    mock_fastmcp_instance.tool = _tool_decorator
    mock_fastmcp.return_value = mock_fastmcp_instance

    mock_mcp_pkg.server.fastmcp.FastMCP = mock_fastmcp
    sys.modules.setdefault("mcp", mock_mcp_pkg)
    sys.modules.setdefault("mcp.server", mock_mcp_pkg.server)
    sys.modules.setdefault("mcp.server.fastmcp", mock_mcp_pkg.server.fastmcp)

    # Remove any cached server module so we get a fresh import
    sys.modules.pop("server", None)

    if str(_MCP_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(_MCP_SERVER_DIR))

    import server  # noqa: F401
    return server


@pytest.fixture(scope="module")
def srv():
    """Module-level fixture: imported server module with mocked mcp."""
    return _load_server()


# ── TestPriorityKey ───────────────────────────────────────────────────────────


class TestPriorityKey:
    """priority_key(priority) — maps P1/P2/P3 to clawteam key strings."""

    def test_p1_maps_to_urgent(self, srv):
        assert srv.priority_key("P1") == "urgent"

    def test_p2_maps_to_normal(self, srv):
        assert srv.priority_key("P2") == "normal"

    def test_p3_maps_to_low(self, srv):
        assert srv.priority_key("P3") == "low"

    def test_unknown_maps_to_normal(self, srv):
        assert srv.priority_key("P99") == "normal"
        assert srv.priority_key("") == "normal"
        assert srv.priority_key("CRITICAL") == "normal"


# ── TestRunClawteam ───────────────────────────────────────────────────────────


class TestRunClawteam:
    """run_clawteam(*args) — subprocess wrapper for clawteam CLI."""

    def test_returns_tuple_of_returncode_stdout_stderr(self, srv):
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
            rc, out, err = srv.run_clawteam("inbox", "send")
        assert rc == 0
        assert out == "ok\n"
        assert err == ""

    def test_nonzero_returncode_passed_through(self, srv):
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
            rc, out, err = srv.run_clawteam("bad-command")
        assert rc == 1
        assert "error msg" in err

    def test_clawteam_binary_used(self, srv):
        """Verify the configured clawteam binary is called."""
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            srv.run_clawteam("inbox", "peek")
        args = mock_run.call_args[0][0]
        assert args[0] == srv.CLAWTEAM
        assert "inbox" in args
        assert "peek" in args


# ── TestRunClawteamJson ───────────────────────────────────────────────────────


class TestRunClawteamJson:
    """run_clawteam_json(*args) — run with --json flag, parse output."""

    def test_returns_parsed_dict_on_success(self, srv):
        payload = {"members": [{"name": "pepper"}]}
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps(payload), stderr=""
            )
            data, err = srv.run_clawteam_json("team", "status")
        assert data == payload
        assert err is None

    def test_returns_none_and_error_on_nonzero(self, srv):
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="team not found")
            data, err = srv.run_clawteam_json("team", "status")
        assert data is None
        assert "team not found" in err

    def test_returns_none_on_invalid_json(self, srv):
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="not-json", stderr="")
            data, err = srv.run_clawteam_json("team", "status")
        assert data is None
        assert err is not None

    def test_json_flag_included_in_command(self, srv):
        with patch("server.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
            srv.run_clawteam_json("inbox", "peek")
        args = mock_run.call_args[0][0]
        assert "--json" in args


# ── TestSoulSendMessage ───────────────────────────────────────────────────────


class TestSoulSendMessage:
    """soul_send_message(to, message, priority) — send a message to an agent."""

    def test_returns_success_message_on_zero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "Message sent to shuri [P2]", "")
            result = srv.soul_send_message("shuri", "hello", priority="P2")
        assert "shuri" in result or "Message sent" in result

    def test_returns_error_on_nonzero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (1, "", "agent not found")
            result = srv.soul_send_message("unknown-agent", "msg")
        assert "ERROR" in result

    def test_uses_priority_key_translation(self, srv):
        """P1 priority must translate to 'urgent' in the clawteam call."""
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "sent", "")
            srv.soul_send_message("pepper", "urgent msg", priority="P1")
        call_args = mock_ct.call_args[0]
        assert "urgent" in call_args

    def test_recipient_included_in_clawteam_args(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "", "")
            srv.soul_send_message("fury", "hello")
        call_args = mock_ct.call_args[0]
        assert "fury" in call_args

    def test_message_content_included_in_args(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "", "")
            srv.soul_send_message("happy", "test-message-content")
        call_args = mock_ct.call_args[0]
        assert "test-message-content" in call_args


# ── TestSoulCheckInbox ────────────────────────────────────────────────────────


class TestSoulCheckInbox:
    """soul_check_inbox(unread_only) — read agent inbox."""

    def test_returns_no_messages_string_when_empty(self, srv):
        with patch("server.run_clawteam_json") as mock_ct:
            mock_ct.return_value = ([], None)
            result = srv.soul_check_inbox(unread_only=False)
        assert "empty" in result.lower() or "no" in result.lower()

    def test_formats_messages_from_clawteam(self, srv):
        msgs = [{"from": "shuri", "text": "hi", "timestamp": "2026-04-08T10:00:00Z",
                 "key": "normal", "read": False}]
        with patch("server.run_clawteam_json") as mock_ct:
            mock_ct.return_value = (msgs, None)
            result = srv.soul_check_inbox(unread_only=False)
        assert "shuri" in result

    def test_unread_only_filters_read_messages(self, srv):
        msgs = [
            {"from": "a", "text": "old", "timestamp": "2026-04-08T10:00:00Z", "key": "normal", "read": True},
            {"from": "b", "text": "new", "timestamp": "2026-04-08T11:00:00Z", "key": "normal", "read": False},
        ]
        with patch("server.run_clawteam_json") as mock_ct:
            mock_ct.return_value = (msgs, None)
            result = srv.soul_check_inbox(unread_only=True)
        assert "b" in result
        # Read message from "a" should not be shown when unread_only=True
        assert "old" not in result


# ── TestSoulBroadcast ─────────────────────────────────────────────────────────


class TestSoulBroadcast:
    """soul_broadcast(message) — send to all agents."""

    def test_returns_success_on_zero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "Broadcast sent", "")
            result = srv.soul_broadcast("team standup in 5 min")
        assert "Broadcast" in result or "sent" in result.lower()

    def test_returns_error_on_nonzero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (1, "", "broadcast failed")
            result = srv.soul_broadcast("message")
        assert "ERROR" in result


# ── TestSoulTaskCreate ────────────────────────────────────────────────────────


class TestSoulTaskCreate:
    """soul_task_create(title, assign, blocked_by) — create team task."""

    def test_returns_success_string(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "Task created: STQA Phase A", "")
            result = srv.soul_task_create("STQA Phase A")
        assert result  # non-empty

    def test_includes_owner_when_specified(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "", "")
            srv.soul_task_create("Task", assign="happy")
        args = mock_ct.call_args[0]
        assert "happy" in args

    def test_returns_error_on_nonzero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (1, "", "create failed")
            result = srv.soul_task_create("Bad Task")
        assert "ERROR" in result


# ── TestSoulTaskUpdate ────────────────────────────────────────────────────────


class TestSoulTaskUpdate:
    """soul_task_update(task_id, status) — update task status."""

    def test_returns_success_on_zero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "Task 42 updated to completed.", "")
            result = srv.soul_task_update("42", "completed")
        assert result

    def test_includes_task_id_in_args(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "", "")
            srv.soul_task_update("99", "in_progress")
        args = mock_ct.call_args[0]
        assert "99" in args

    def test_includes_status_in_args(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (0, "", "")
            srv.soul_task_update("1", "completed")
        args = mock_ct.call_args[0]
        assert "completed" in args

    def test_returns_error_on_nonzero_rc(self, srv):
        with patch("server.run_clawteam") as mock_ct:
            mock_ct.return_value = (1, "", "task not found")
            result = srv.soul_task_update("999", "done")
        assert "ERROR" in result


# ── TestGetTeamConfigPath ─────────────────────────────────────────────────────


class TestGetTeamConfigPath:
    """_get_team_config_path() — resolve native team config path."""

    def test_returns_path_from_env_var(self, srv, tmp_path, monkeypatch):
        custom = str(tmp_path / "custom-config.json")
        with patch.dict("os.environ", {"SOUL_TEAM_CONFIG": custom}):
            result = srv._get_team_config_path()
        assert str(result) == custom

    def test_returns_path_object(self, srv):
        result = srv._get_team_config_path()
        assert isinstance(result, Path)

    def test_uses_default_when_no_env_var(self, srv, monkeypatch):
        with patch.dict("os.environ", {}, clear=True):
            result = srv._get_team_config_path()
        # Should be a path under ~/.claude/teams/
        assert "teams" in str(result) or ".claude" in str(result)


# ── TestMCPCreateApp (pending Forge) ──────────────────────────────────────────


class TestMCPCreateApp:
    """create_app() factory — returns FastMCP instance without starting server.

    Pending STQA Phase 0 ST-PRE-01: Forge must add create_app() to server.py.
    """

    @pytest.mark.skip(reason="Waiting for Forge: create_app() factory not yet in mcp-server/server.py (STQA ST-PRE-01)")
    def test_create_app_importable(self, srv):
        from server import create_app  # noqa — will exist after Forge delivery
        assert callable(create_app)

    @pytest.mark.skip(reason="Waiting for Forge: create_app() factory not yet in mcp-server/server.py (STQA ST-PRE-01)")
    def test_create_app_returns_fastmcp_instance(self, srv):
        from server import create_app  # noqa
        app = create_app()
        assert app is not None

    @pytest.mark.skip(reason="Waiting for Forge: create_app() factory not yet in mcp-server/server.py (STQA ST-PRE-01)")
    def test_create_app_idempotent(self, srv):
        """Multiple calls must return equivalent apps without side effects."""
        from server import create_app  # noqa
        app1 = create_app()
        app2 = create_app()
        assert type(app1) == type(app2)
