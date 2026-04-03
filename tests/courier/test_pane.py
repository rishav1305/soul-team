"""Tests for PaneManager — tmux pane state detection, injection, verification."""
import time
from unittest.mock import patch, MagicMock
from soul_courier.pane import PaneManager


def _make_pm(panes=None):
    return PaneManager(panes or {"fury": "%10", "hawkeye": "%11"})


def test_detect_state_dead_no_pane():
    pm = _make_pm({"fury": "%10"})
    assert pm.detect_state("nonexistent") == "dead"


def test_detect_state_dead_capture_fails():
    pm = _make_pm()
    with patch.object(pm, "_tmux_capture", return_value=None):
        assert pm.detect_state("fury") == "dead"


def test_detect_state_crashed():
    pm = _make_pm()
    content = "some output\nuser@host:~$ \n"
    with patch.object(pm, "_tmux_capture", return_value=content):
        assert pm.detect_state("fury") == "crashed"


def test_detect_state_idle_prompt():
    pm = _make_pm()
    content = "some output\n\u276f \nstatus bar line"
    with patch.object(pm, "_tmux_capture", return_value=content):
        assert pm.detect_state("fury") == "idle"


def test_detect_state_idle_ascii_prompt():
    pm = _make_pm()
    content = "some output\n> \nstatus bar"
    with patch.object(pm, "_tmux_capture", return_value=content):
        assert pm.detect_state("fury") == "idle"


def test_detect_state_crunched():
    pm = _make_pm()
    content = "Crunched previous messages\n\u276f \nstatus"
    with patch.object(pm, "_tmux_capture", return_value=content):
        assert pm.detect_state("fury") == "crunched"


def test_detect_state_cache_hit():
    pm = _make_pm()
    content = "\u276f \nstatus"
    with patch.object(pm, "_tmux_capture", return_value=content) as mock_cap:
        assert pm.detect_state("fury") == "idle"
        assert pm.detect_state("fury") == "idle"
        assert mock_cap.call_count == 1


def test_detect_state_cache_expired():
    pm = _make_pm()
    content = "\u276f \nstatus"
    with patch.object(pm, "_tmux_capture", return_value=content) as mock_cap:
        assert pm.detect_state("fury") == "idle"
        pm._state_cache["fury"] = ("idle", time.monotonic() - 5.0)
        assert pm.detect_state("fury") == "idle"
        assert mock_cap.call_count == 2


def test_inject_uses_send_keys():
    """Short messages use send-keys -l (literal) for reliable delivery."""
    pm = _make_pm()
    with patch("subprocess.run") as mock_run, patch("time.sleep"):
        mock_run.return_value = MagicMock(returncode=0)
        result = pm.inject("fury", "hello world")
        assert result is True
        # send-keys -l, Enter (safety-net second Enter removed in Phase 1E)
        assert mock_run.call_count == 2
        first_call = mock_run.call_args_list[0]
        assert "-l" in first_call.args[0]
        assert "hello world" in first_call.args[0]


def test_inject_falls_back_to_paste_buffer_for_large_messages():
    """Messages exceeding SENDKEYS_MAX_CHARS use paste-buffer fallback."""
    pm = _make_pm()
    large_msg = "x" * (pm.SENDKEYS_MAX_CHARS + 100)
    with patch("subprocess.run") as mock_run, patch("time.sleep"), \
         patch("tempfile.mkstemp", return_value=(999, "/tmp/test.txt")), \
         patch("os.fdopen", return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())), \
         patch("os.unlink"):
        mock_run.return_value = MagicMock(returncode=0)
        result = pm.inject("fury", large_msg)
        assert result is True
        # load-buffer, paste-buffer, Enter (safety-net second Enter removed in Phase 1E)
        assert mock_run.call_count == 3
        load_call = mock_run.call_args_list[0]
        assert "load-buffer" in load_call.args[0]
        assert "courier-fury" in load_call.args[0]


def test_inject_delay_scales_with_message_size():
    """Longer messages get more delay before Enter to let TUI process input."""
    pm = _make_pm()
    sleep_calls = []
    with patch("subprocess.run") as mock_run, \
         patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        mock_run.return_value = MagicMock(returncode=0)
        # 30-line message should get ~1.2s delay (0.3 + 30*0.03)
        long_msg = "\n".join(f"line {i}" for i in range(30))
        pm.inject("fury", long_msg)
        # Only the scaled delay remains (safety-net 0.4s sleep removed in Phase 1E)
        assert sleep_calls[0] >= 1.0  # 0.3 base + 30*0.03 = 1.2

        sleep_calls.clear()
        # Short message should get ~0.33s delay (0.3 + 1*0.03)
        pm.inject("fury", "short")
        assert sleep_calls[0] <= 0.4


def test_verify_injection_success():
    pm = _make_pm()
    with patch.object(pm, "_tmux_capture", return_value="[INBOX] From: team-lead | blah"):
        with patch("time.sleep"):
            assert pm.verify_injection("fury", "From: team-lead") is True


def test_verify_injection_failure():
    pm = _make_pm()
    with patch.object(pm, "_tmux_capture", return_value="some unrelated output"):
        with patch("time.sleep"):
            assert pm.verify_injection("fury", "From: team-lead") is False


def test_update_panes_preserves_locks():
    pm = _make_pm()
    old_lock = pm.locks["fury"]
    pm.update_panes({"fury": "%20", "loki": "%21"})
    assert pm.panes["fury"] == "%20"
    assert pm.panes["loki"] == "%21"
    assert "hawkeye" not in pm.panes
    # Old lock preserved for fury (not recreated)
    assert pm.locks["fury"] is old_lock
    # New lock created for loki
    assert "loki" in pm.locks


def test_mark_dead():
    pm = _make_pm()
    pm.mark_dead("fury")
    assert pm.detect_state("fury") == "dead"


def test_invalidate_cache():
    pm = _make_pm()
    content = "\u276f \nstatus"
    with patch.object(pm, "_tmux_capture", return_value=content) as mock_cap:
        pm.detect_state("fury")
        assert mock_cap.call_count == 1
        pm.invalidate_cache("fury")
        pm.detect_state("fury")
        assert mock_cap.call_count == 2
