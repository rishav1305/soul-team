"""
test_router.py -- Tests for soul-router.py

Covers:
  1. BroadcastHandler — fan-out to all agents, dedup via _seen set
  2. DiscussionHandler — thread creation, response handling, limits
  3. DirectHandler / write_to_inbox — direct message routing
  4. Agent list and config constants
  5. Utility functions (slugify, utcnow, load_json, save_json, ensure_dirs)
  6. Fan-out cooldown and dedup logic
  7. Thread lifecycle (create, close, auto-close)
  8. Crash recovery

Run:
    cd ~/.claude/scripts && python3 -m pytest tests/test_router.py -v --timeout=10
"""

import json
import os
import sys
import time
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Setup: import the router module
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the router module
soul_router = importlib.import_module("soul-router")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_team_dir(tmp_path):
    """Set up a temporary team directory structure."""
    team_dir = tmp_path / "soul-team"
    inboxes = team_dir / "inboxes"
    broadcast = team_dir / "broadcast"
    discussions = team_dir / "discussions"
    sidecar = team_dir / "sidecar"
    for d in [team_dir, inboxes, broadcast, discussions, sidecar]:
        d.mkdir(parents=True, exist_ok=True)
    for agent in soul_router.ALL_AGENTS + ["team-lead"]:
        inbox = inboxes / f"{agent}_{agent}"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "archive").mkdir(exist_ok=True)
    return team_dir


@pytest.fixture(autouse=True)
def reset_router_state():
    """Reset mutable module-level state between tests."""
    soul_router._fanned_ids.clear()
    soul_router._pending_fanouts.clear()
    # Cancel any lingering timers
    for t in soul_router._fanout_timers.values():
        t.cancel()
    soul_router._fanout_timers.clear()
    yield


@pytest.fixture
def patched_dirs(tmp_team_dir):
    """Patch all directory constants to use tmp_team_dir."""
    inboxes = tmp_team_dir / "inboxes"
    broadcast = tmp_team_dir / "broadcast"
    discussions = tmp_team_dir / "discussions"
    sidecar = tmp_team_dir / "sidecar"

    with patch.object(soul_router, "TEAM_DIR", tmp_team_dir), \
         patch.object(soul_router, "INBOXES_DIR", inboxes), \
         patch.object(soul_router, "BROADCAST_DIR", broadcast), \
         patch.object(soul_router, "DISCUSSIONS_DIR", discussions), \
         patch.object(soul_router, "SIDECAR_DIR", sidecar):
        yield tmp_team_dir


# ===========================================================================
# 1. Agent List & Constants
# ===========================================================================

class TestConstants:
    """Tests for module constants and configuration."""

    def test_all_agents_count(self):
        """ALL_AGENTS contains exactly 9 agents."""
        assert len(soul_router.ALL_AGENTS) == 9

    def test_all_agents_known_names(self):
        """ALL_AGENTS contains all expected agent names."""
        expected = {"happy", "xavier", "hawkeye", "pepper",
                    "fury", "loki", "shuri", "stark", "banner"}
        assert set(soul_router.ALL_AGENTS) == expected

    def test_max_messages_per_thread(self):
        """MAX_MESSAGES_PER_THREAD is a positive integer."""
        assert soul_router.MAX_MESSAGES_PER_THREAD > 0
        assert isinstance(soul_router.MAX_MESSAGES_PER_THREAD, int)

    def test_max_concurrent_discussions(self):
        """MAX_CONCURRENT_DISCUSSIONS is a positive integer."""
        assert soul_router.MAX_CONCURRENT_DISCUSSIONS > 0

    def test_fan_out_cooldown_positive(self):
        """FAN_OUT_COOLDOWN_SECS is positive."""
        assert soul_router.FAN_OUT_COOLDOWN_SECS > 0


# ===========================================================================
# 2. Utility Functions
# ===========================================================================

class TestUtilities:
    """Tests for slugify, utcnow, load_json, save_json."""

    def test_slugify_basic(self):
        """slugify converts topic to filesystem-safe slug."""
        assert soul_router.slugify("Hello World") == "hello-world"

    def test_slugify_special_chars(self):
        """slugify removes special characters."""
        assert soul_router.slugify("What's the plan?!") == "whats-the-plan"

    def test_slugify_long_text_truncated(self):
        """slugify truncates to 60 chars."""
        long_topic = "a" * 100
        result = soul_router.slugify(long_topic)
        assert len(result) <= 60

    def test_slugify_multiple_spaces(self):
        """slugify collapses multiple spaces/underscores to single dash."""
        assert soul_router.slugify("hello   world__test") == "hello-world-test"

    def test_slugify_strip_dashes(self):
        """slugify strips leading/trailing dashes."""
        assert soul_router.slugify("--test--") == "test"

    def test_slugify_empty(self):
        """slugify handles empty string."""
        assert soul_router.slugify("") == ""

    def test_utcnow_format(self):
        """utcnow returns ISO 8601 UTC timestamp."""
        result = soul_router.utcnow()
        assert result.endswith("Z")
        assert "T" in result
        assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ

    def test_load_json_valid(self, tmp_path):
        """load_json reads valid JSON file."""
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}')
        result = soul_router.load_json(f)
        assert result == {"key": "value"}

    def test_load_json_invalid(self, tmp_path):
        """load_json returns None for invalid JSON."""
        f = tmp_path / "bad.json"
        f.write_text("not json {{")
        result = soul_router.load_json(f)
        assert result is None

    def test_load_json_missing_file(self, tmp_path):
        """load_json returns None for missing file."""
        result = soul_router.load_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_save_json_roundtrip(self, tmp_path):
        """save_json writes JSON that load_json can read back."""
        f = tmp_path / "roundtrip.json"
        data = {"thread_id": "test-123", "status": "active"}
        soul_router.save_json(f, data)
        result = soul_router.load_json(f)
        assert result == data

    def test_save_json_atomic(self, tmp_path):
        """save_json uses atomic rename (no .tmp left behind)."""
        f = tmp_path / "atomic.json"
        soul_router.save_json(f, {"a": 1})
        assert f.exists()
        assert not f.with_suffix(".tmp").exists()


# ===========================================================================
# 3. ensure_dirs
# ===========================================================================

class TestEnsureDirs:
    """Tests for ensure_dirs() directory creation."""

    def test_ensure_dirs_creates_structure(self, tmp_path):
        """ensure_dirs creates all required directories."""
        with patch.object(soul_router, "TEAM_DIR", tmp_path / "team"), \
             patch.object(soul_router, "INBOXES_DIR", tmp_path / "team" / "inboxes"), \
             patch.object(soul_router, "BROADCAST_DIR", tmp_path / "team" / "broadcast"), \
             patch.object(soul_router, "DISCUSSIONS_DIR", tmp_path / "team" / "discussions"), \
             patch.object(soul_router, "SIDECAR_DIR", tmp_path / "team" / "sidecar"):
            soul_router.ensure_dirs()
            assert (tmp_path / "team" / "inboxes").is_dir()
            assert (tmp_path / "team" / "broadcast").is_dir()
            assert (tmp_path / "team" / "discussions").is_dir()
            assert (tmp_path / "team" / "sidecar").is_dir()

    def test_ensure_dirs_creates_agent_inboxes(self, tmp_path):
        """ensure_dirs creates inbox for each agent and team-lead."""
        inboxes = tmp_path / "inboxes"
        with patch.object(soul_router, "TEAM_DIR", tmp_path), \
             patch.object(soul_router, "INBOXES_DIR", inboxes), \
             patch.object(soul_router, "BROADCAST_DIR", tmp_path / "broadcast"), \
             patch.object(soul_router, "DISCUSSIONS_DIR", tmp_path / "discussions"), \
             patch.object(soul_router, "SIDECAR_DIR", tmp_path / "sidecar"):
            soul_router.ensure_dirs()
            for agent in soul_router.ALL_AGENTS + ["team-lead"]:
                inbox = inboxes / f"{agent}_{agent}"
                assert inbox.is_dir()
                assert (inbox / "archive").is_dir()


# ===========================================================================
# 4. write_to_inbox
# ===========================================================================

class TestWriteToInbox:
    """Tests for write_to_inbox() direct message routing."""

    def test_write_creates_file(self, patched_dirs):
        """write_to_inbox creates a JSON file in the agent's inbox."""
        msg = {"from": "team-lead", "content": "Hello happy"}
        result = soul_router.write_to_inbox("happy", msg, "test-msg.json")
        assert result is True
        inbox = patched_dirs / "inboxes" / "happy_happy"
        assert (inbox / "test-msg.json").exists()
        data = json.loads((inbox / "test-msg.json").read_text())
        assert data["from"] == "team-lead"

    def test_write_auto_generates_filename(self, patched_dirs):
        """write_to_inbox generates timestamp filename when none given."""
        msg = {"from": "fury", "content": "Status?"}
        result = soul_router.write_to_inbox("shuri", msg)
        assert result is True
        inbox = patched_dirs / "inboxes" / "shuri_shuri"
        files = list(inbox.glob("*.json"))
        assert len(files) == 1
        assert files[0].name.endswith("-router.json")

    def test_write_creates_inbox_if_missing(self, patched_dirs):
        """write_to_inbox creates inbox directory if it doesn't exist."""
        new_inbox = patched_dirs / "inboxes" / "newagent_newagent"
        if new_inbox.exists():
            import shutil
            shutil.rmtree(new_inbox)
        msg = {"from": "test", "content": "hi"}
        result = soul_router.write_to_inbox("newagent", msg, "test.json")
        assert result is True

    def test_write_returns_false_on_error(self, patched_dirs):
        """write_to_inbox returns False when write fails."""
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = soul_router.write_to_inbox("happy", {"from": "test"}, "test.json")
        assert result is False


# ===========================================================================
# 5. Fanned ID Tracking (dedup)
# ===========================================================================

class TestFannedTracking:
    """Tests for is_fanned() and mark_fanned() dedup logic."""

    def test_not_fanned_initially(self):
        """New message IDs are not in the fanned set."""
        assert soul_router.is_fanned("thread-1", "msg-123") is False

    def test_mark_and_check_fanned(self):
        """mark_fanned adds ID, is_fanned detects it."""
        soul_router.mark_fanned("thread-1", "msg-123")
        assert soul_router.is_fanned("thread-1", "msg-123") is True

    def test_fanned_per_thread(self):
        """Fanned IDs are scoped per thread."""
        soul_router.mark_fanned("thread-1", "msg-1")
        assert soul_router.is_fanned("thread-1", "msg-1") is True
        assert soul_router.is_fanned("thread-2", "msg-1") is False

    def test_multiple_fanned_ids(self):
        """Multiple IDs can be fanned for one thread."""
        for i in range(5):
            soul_router.mark_fanned("thread-1", f"msg-{i}")
        for i in range(5):
            assert soul_router.is_fanned("thread-1", f"msg-{i}") is True
        assert soul_router.is_fanned("thread-1", "msg-999") is False


# ===========================================================================
# 6. BroadcastHandler
# ===========================================================================

class TestBroadcastHandler:
    """Tests for BroadcastHandler fan-out logic."""

    def test_handler_init(self):
        """BroadcastHandler initializes with empty _seen set."""
        handler = soul_router.BroadcastHandler()
        assert handler._seen == set()

    def test_handle_broadcast_fans_out(self, patched_dirs):
        """_handle_broadcast writes to all agent inboxes."""
        handler = soul_router.BroadcastHandler()
        msg_file = patched_dirs / "broadcast" / "test-broadcast.json"
        msg = {"from": "team-lead", "content": "Status check", "type": "broadcast"}
        msg_file.write_text(json.dumps(msg))

        handler._handle_broadcast(msg_file)

        # Check all 9 agents got the message
        for agent in soul_router.ALL_AGENTS:
            inbox = patched_dirs / "inboxes" / f"{agent}_{agent}"
            files = list(inbox.glob("*-broadcast.json"))
            assert len(files) == 1, f"Agent {agent} missing broadcast"
            data = json.loads(files[0].read_text())
            assert data["type"] == "broadcast"
            assert data["to"] == agent

    def test_broadcast_dedup(self, patched_dirs):
        """BroadcastHandler skips duplicate filenames."""
        handler = soul_router.BroadcastHandler()
        msg_file = patched_dirs / "broadcast" / "dup-test.json"
        msg = {"from": "team-lead", "content": "First"}
        msg_file.write_text(json.dumps(msg))

        handler._handle_broadcast(msg_file)
        # Call again -- should skip (filename already in _seen)
        handler._seen.add("dup-test.json")

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(msg_file)
        handler.on_created(event)

        # Should still only have 1 message per agent
        inbox = patched_dirs / "inboxes" / "happy_happy"
        files = list(inbox.glob("*-broadcast.json"))
        assert len(files) == 1

    def test_on_created_ignores_directories(self):
        """BroadcastHandler.on_created ignores directory events."""
        handler = soul_router.BroadcastHandler()
        event = MagicMock()
        event.is_directory = True
        # Should not raise or process
        handler.on_created(event)

    def test_on_created_ignores_non_json(self):
        """BroadcastHandler.on_created ignores non-JSON files."""
        handler = soul_router.BroadcastHandler()
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.txt"
        handler.on_created(event)
        assert "test.txt" not in handler._seen

    def test_on_moved_handles_atomic_rename(self, patched_dirs):
        """BroadcastHandler.on_moved handles atomic tmp->final renames."""
        handler = soul_router.BroadcastHandler()
        msg_file = patched_dirs / "broadcast" / "moved-test.json"
        msg = {"from": "team-lead", "content": "Moved"}
        msg_file.write_text(json.dumps(msg))

        event = MagicMock()
        event.is_directory = False
        event.dest_path = str(msg_file)
        handler.on_moved(event)

        assert "moved-test.json" in handler._seen


# ===========================================================================
# 7. DiscussionHandler — Thread Creation
# ===========================================================================

class TestDiscussionHandler:
    """Tests for DiscussionHandler thread management."""

    def test_handler_init(self):
        """DiscussionHandler initializes with empty tracking sets."""
        handler = soul_router.DiscussionHandler()
        assert handler._seen_top == set()
        assert handler._watched_threads == set()

    def test_create_thread(self, patched_dirs):
        """_create_thread creates thread directory, state.json, fans out opening."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"

        msg = {
            "action": "create",
            "topic": "Architecture Review",
            "content": "Let's discuss the new design",
            "from": "team-lead",
            "participants": ["all"],
        }

        with patch.object(handler, "_watch_thread"):
            handler._create_thread(msg)

        # Find the thread directory
        thread_dirs = [d for d in discussions.iterdir() if d.is_dir()]
        assert len(thread_dirs) == 1
        thread_dir = thread_dirs[0]
        assert "architecture-review" in thread_dir.name

        # Check state.json
        state = json.loads((thread_dir / "state.json").read_text())
        assert state["topic"] == "Architecture Review"
        assert state["status"] == "active"
        assert state["started_by"] == "team-lead"
        assert len(state["participants"]) == 9

    def test_create_thread_specific_participants(self, patched_dirs):
        """_create_thread with specific participants only fans out to them."""
        handler = soul_router.DiscussionHandler()

        msg = {
            "action": "create",
            "topic": "Frontend sync",
            "content": "UI work",
            "from": "team-lead",
            "participants": ["happy", "shuri"],
        }

        with patch.object(handler, "_watch_thread"):
            handler._create_thread(msg)

        discussions = patched_dirs / "discussions"
        thread_dirs = [d for d in discussions.iterdir() if d.is_dir()]
        assert len(thread_dirs) == 1

        state = json.loads((thread_dirs[0] / "state.json").read_text())
        assert set(state["participants"]) == {"happy", "shuri"}

    def test_create_thread_max_concurrent_blocks(self, patched_dirs):
        """Thread creation blocked when MAX_CONCURRENT_DISCUSSIONS reached."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"

        # Create MAX_CONCURRENT_DISCUSSIONS active threads
        for i in range(soul_router.MAX_CONCURRENT_DISCUSSIONS):
            thread_dir = discussions / f"thread-{i}"
            thread_dir.mkdir()
            soul_router.save_json(
                thread_dir / "state.json",
                {"thread_id": f"thread-{i}", "status": "active", "participants": ["happy"]},
            )

        msg = {
            "action": "create",
            "topic": "One too many",
            "content": "Should be blocked",
            "from": "team-lead",
            "participants": ["all"],
        }

        with patch.object(handler, "_watch_thread"):
            handler._create_thread(msg)

        # Should NOT have created a new thread (only the pre-existing ones)
        thread_dirs = [d for d in discussions.iterdir() if d.is_dir()]
        assert len(thread_dirs) == soul_router.MAX_CONCURRENT_DISCUSSIONS

    def test_close_thread_request(self, patched_dirs):
        """_close_thread_request closes an active thread."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"

        # Create an active thread
        thread_dir = discussions / "test-close"
        thread_dir.mkdir()
        soul_router.save_json(
            thread_dir / "state.json",
            {"thread_id": "test-close", "status": "active",
             "participants": ["happy"], "message_count": 0},
        )

        handler._close_thread_request({"thread_id": "test-close"})

        state = json.loads((thread_dir / "state.json").read_text())
        assert state["status"] == "closed"

    def test_on_created_ignores_non_json(self):
        """DiscussionHandler.on_created ignores non-JSON files."""
        handler = soul_router.DiscussionHandler()
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/not-json.txt"
        handler.on_created(event)
        assert len(handler._seen_top) == 0

    def test_on_created_ignores_subdirectory_files(self, patched_dirs):
        """DiscussionHandler.on_created ignores files in thread subdirectories."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"
        sub = discussions / "some-thread"
        sub.mkdir()

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(sub / "response.json")
        # The handler checks if path.parent == DISCUSSIONS_DIR
        with patch.object(soul_router, "DISCUSSIONS_DIR", discussions):
            handler.on_created(event)
        assert len(handler._seen_top) == 0


# ===========================================================================
# 8. ThreadResponseHandler
# ===========================================================================

class TestThreadResponseHandler:
    """Tests for ThreadResponseHandler response fan-out."""

    def test_handler_init(self):
        """ThreadResponseHandler initializes with thread_id and empty _seen."""
        handler = soul_router.ThreadResponseHandler("test-thread")
        assert handler.thread_id == "test-thread"
        assert handler._seen == set()

    def test_ignores_state_json(self):
        """ThreadResponseHandler skips state.json files."""
        handler = soul_router.ThreadResponseHandler("test-thread")
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/discussions/test-thread/state.json"
        handler.on_created(event)
        assert "state.json" not in handler._seen

    def test_on_moved_handles_rename(self):
        """ThreadResponseHandler.on_moved handles atomic renames."""
        handler = soul_router.ThreadResponseHandler("test-thread")
        event = MagicMock()
        event.is_directory = False
        event.dest_path = "/tmp/discussions/test-thread/123-happy.json"

        with patch.object(handler, "_handle_response") as mock_hr:
            handler.on_moved(event)

        assert "123-happy.json" in handler._seen


# ===========================================================================
# 9. count_active_discussions
# ===========================================================================

class TestCountActiveDiscussions:
    """Tests for count_active_discussions()."""

    def test_empty_discussions_dir(self, patched_dirs):
        """Returns 0 when no threads exist."""
        assert soul_router.count_active_discussions() == 0

    def test_counts_active_only(self, patched_dirs):
        """Counts only threads with status 'active'."""
        discussions = patched_dirs / "discussions"

        for i, status in enumerate(["active", "closed", "active"]):
            thread_dir = discussions / f"thread-{i}"
            thread_dir.mkdir()
            soul_router.save_json(
                thread_dir / "state.json",
                {"thread_id": f"thread-{i}", "status": status},
            )

        assert soul_router.count_active_discussions() == 2


# ===========================================================================
# 10. _close_thread
# ===========================================================================

class TestCloseThread:
    """Tests for _close_thread() lifecycle management."""

    def test_close_sets_status(self, patched_dirs):
        """_close_thread sets status to 'closed' in state.json."""
        discussions = patched_dirs / "discussions"
        thread_dir = discussions / "close-test"
        thread_dir.mkdir()

        state = {
            "thread_id": "close-test",
            "status": "active",
            "participants": ["happy", "shuri"],
            "message_count": 5,
        }
        state_path = thread_dir / "state.json"
        soul_router.save_json(state_path, state)

        soul_router._close_thread("close-test", state, "Test closure")

        updated = json.loads(state_path.read_text())
        assert updated["status"] == "closed"

    def test_close_notifies_participants(self, patched_dirs):
        """_close_thread sends close notification to all participants + team-lead."""
        discussions = patched_dirs / "discussions"
        thread_dir = discussions / "notify-test"
        thread_dir.mkdir()

        state = {
            "thread_id": "notify-test",
            "status": "active",
            "participants": ["happy"],
            "message_count": 3,
        }
        soul_router.save_json(thread_dir / "state.json", state)

        soul_router._close_thread("notify-test", state, "Done")

        # Check happy got a close notification
        inbox = patched_dirs / "inboxes" / "happy_happy"
        close_files = list(inbox.glob("*-close.json"))
        assert len(close_files) >= 1

        # Check team-lead also got notified
        tl_inbox = patched_dirs / "inboxes" / "team-lead_team-lead"
        tl_close = list(tl_inbox.glob("*-close.json"))
        assert len(tl_close) >= 1


# ===========================================================================
# 11. Crash Recovery
# ===========================================================================

class TestCrashRecovery:
    """Tests for crash_recovery() on startup."""

    def test_recovery_resumes_active_threads(self, patched_dirs):
        """crash_recovery watches active threads."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"

        thread_dir = discussions / "active-thread"
        thread_dir.mkdir()
        soul_router.save_json(
            thread_dir / "state.json",
            {"thread_id": "active-thread", "status": "active",
             "participants": ["happy"], "message_count": 0},
        )

        with patch.object(handler, "_watch_thread") as mock_watch:
            soul_router.crash_recovery(handler)

        mock_watch.assert_called_once_with("active-thread")

    def test_recovery_skips_closed_threads(self, patched_dirs):
        """crash_recovery ignores closed threads."""
        handler = soul_router.DiscussionHandler()
        discussions = patched_dirs / "discussions"

        thread_dir = discussions / "closed-thread"
        thread_dir.mkdir()
        soul_router.save_json(
            thread_dir / "state.json",
            {"thread_id": "closed-thread", "status": "closed",
             "participants": ["happy"], "message_count": 10},
        )

        with patch.object(handler, "_watch_thread") as mock_watch:
            soul_router.crash_recovery(handler)

        mock_watch.assert_not_called()


# ===========================================================================
# 12. schedule_fanout / _flush_fanout
# ===========================================================================

class TestFanoutScheduling:
    """Tests for batched fan-out cooldown logic."""

    def test_schedule_creates_timer(self):
        """schedule_fanout creates a pending timer."""
        msg = {"from": "happy", "content": "test"}
        soul_router.schedule_fanout("thread-1", msg, "test.json", "happy")
        assert "thread-1" in soul_router._pending_fanouts
        assert len(soul_router._pending_fanouts["thread-1"]) == 1
        # Clean up timer
        if "thread-1" in soul_router._fanout_timers:
            soul_router._fanout_timers["thread-1"].cancel()

    def test_flush_skips_closed_thread(self, patched_dirs):
        """_flush_fanout skips fan-out for closed threads."""
        discussions = patched_dirs / "discussions"
        thread_dir = discussions / "closed-flush"
        thread_dir.mkdir()
        soul_router.save_json(
            thread_dir / "state.json",
            {"thread_id": "closed-flush", "status": "closed",
             "participants": ["happy"], "message_count": 5},
        )

        # Manually set up pending fanout
        soul_router._pending_fanouts["closed-flush"] = [
            ({"from": "test", "content": "hi"}, "test.json", "test")
        ]

        soul_router._flush_fanout("closed-flush")

        # Should not have written to any inbox
        inbox = patched_dirs / "inboxes" / "happy_happy"
        files = list(inbox.glob("*.json"))
        assert len(files) == 0

    def test_flush_empty_batch(self):
        """_flush_fanout handles empty batch gracefully."""
        soul_router._flush_fanout("nonexistent-thread")
        # Should not raise
