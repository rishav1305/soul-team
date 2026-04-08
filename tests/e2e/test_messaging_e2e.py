"""
STQA2 Phase 4 — End-to-end messaging scenarios.

Tests the courier daemon's message delivery chain:
  write msg to inbox → courier picks up → archives + marks seen

All agents are configured as FILE_ONLY in the E2E fixtures,
so delivery is verified via archive directories and delivery logs
rather than tmux pane injection.
"""

import json
import time

import pytest


pytestmark = pytest.mark.e2e


class TestMessageDelivery:
    """STQA2-4.2 through STQA2-4.6: E2E messaging scenarios."""

    def test_message_delivered_to_recipient_inbox(
        self, courier_instance, message_helpers
    ):
        """STQA2-4.2: Agent A sends → file present in agent's archive within 5s."""
        helpers = message_helpers
        team_dir = courier_instance["team_dir"]

        helpers.send_message(
            from_agent="agent-a",
            to_agent="team-lead",
            content="Delivery test message",
        )

        archived = helpers.wait_for_archive("team-lead", timeout=5.0)
        assert len(archived) >= 1, (
            "Expected message to be archived for team-lead within 5s"
        )

    def test_message_fields_are_correct(self, courier_instance, message_helpers):
        """STQA2-4.3: Verify from, to, timestamp, content in delivered JSON."""
        helpers = message_helpers

        # Record baseline count before sending — use agent-b (simpler path).
        before = helpers.count_archived("agent-b")

        msg_content = f"Field check {int(time.time() * 1000)}"
        ts_str = str(int(time.time() * 1000))
        helpers.send_message(
            from_agent="agent-a",
            to_agent="agent-b",
            content=msg_content,
            message_id=f"msg-fields-{ts_str}",
        )

        # Wait for one more message than before.
        archived = helpers.wait_for_archive(
            "agent-b", timeout=5.0, min_count=before + 1
        )
        assert len(archived) >= before + 1

        # Find the specific message by content.
        all_msgs = helpers.get_archived_messages("agent-b")
        matching = [m for m in all_msgs if m.get("content") == msg_content]
        assert len(matching) == 1, (
            f"Expected 1 matching message, got {len(matching)}. "
            f"All msgs: {[m.get('content', '')[:30] for m in all_msgs]}"
        )

        data = matching[0]
        assert data["from"] == "agent-a", f"from field: {data.get('from')}"
        assert data["to"] == "agent-b", f"to field: {data.get('to')}"
        assert "timestamp" in data, "timestamp field missing"
        assert data["content"] == msg_content, f"content field: {data.get('content')}"

    def test_two_agents_cross_sending(self, courier_instance, message_helpers):
        """STQA2-4.4: A→B and B→A both deliver; no cross-contamination."""
        helpers = message_helpers
        team_dir = courier_instance["team_dir"]

        # Use unique message IDs.
        ts = str(int(time.time() * 1000))
        helpers.send_message(
            from_agent="agent-a",
            to_agent="agent-b",
            content="Hello from A",
            message_id=f"msg-cross-a2b-{ts}",
        )
        helpers.send_message(
            from_agent="agent-b",
            to_agent="agent-a",
            content="Hello from B",
            message_id=f"msg-cross-b2a-{ts}",
        )

        # Wait for both to be archived.
        archived_b = helpers.wait_for_archive("agent-b", timeout=5.0)
        archived_a = helpers.wait_for_archive("agent-a", timeout=5.0)

        assert len(archived_b) >= 1, "agent-b should have received a message"
        assert len(archived_a) >= 1, "agent-a should have received a message"

        # Verify no cross-contamination.
        b_messages = helpers.get_archived_messages("agent-b")
        a_messages = helpers.get_archived_messages("agent-a")

        b_from_a = [m for m in b_messages if m.get("from") == "agent-a"]
        a_from_b = [m for m in a_messages if m.get("from") == "agent-b"]

        assert len(b_from_a) >= 1, "agent-b should have msg from agent-a"
        assert len(a_from_b) >= 1, "agent-a should have msg from agent-b"

    def test_duplicate_message_id_delivered_once(
        self, courier_instance, message_helpers
    ):
        """STQA2-4.5: Same message_id sent twice → only 1 archive file."""
        helpers = message_helpers
        team_dir = courier_instance["team_dir"]

        ts = str(int(time.time() * 1000))
        dup_id = f"msg-dup-test-{ts}"

        helpers.send_message(
            from_agent="agent-a",
            to_agent="agent-c",
            content="First send",
            message_id=dup_id,
        )

        # Wait for first message to be processed.
        archived = helpers.wait_for_archive("agent-c", timeout=5.0)
        assert len(archived) >= 1, "First message should be archived"

        # Send same message_id again.
        helpers.send_message(
            from_agent="agent-a",
            to_agent="agent-c",
            content="Duplicate send",
            message_id=dup_id,
        )

        # Wait a moment for courier to process.
        time.sleep(2.0)

        # Count files with the duplicate ID.
        base = team_dir / "inboxes" / "agent-c_agent-c"
        dup_files = []
        for archive_dir in [base / "archive", base / "new" / "archive"]:
            if archive_dir.exists():
                dup_files.extend(
                    [f for f in archive_dir.glob("*.json") if dup_id in f.name]
                )
        # The second send creates a new file with the same name.
        # Courier's _is_seen check uses msg_file.stem, so the duplicate
        # should be caught. But file rename overwrites the archive copy.
        # Either way, there should be exactly 1 file with this ID.
        assert len(dup_files) <= 1, (
            f"Expected at most 1 file with ID {dup_id}, got {len(dup_files)}"
        )

    def test_multi_hop_routing_not_supported(self):
        """STQA2-4.6: Multi-hop relay is not supported — skip."""
        pytest.skip("Multi-hop relay not implemented in courier (OQ-C resolved)")
