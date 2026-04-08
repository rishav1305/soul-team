"""
STQA2 Phase 3 — Smoke test for E2E harness.

Verifies that the courier daemon starts, picks up a message file,
and processes it (archive + mark seen).
"""

import pytest


pytestmark = pytest.mark.e2e


def test_harness_fixtures_exist(tmp_team_dir, courier_instance, message_helpers):
    """Verify all E2E fixtures are available and courier is running."""
    assert tmp_team_dir.exists()
    assert courier_instance["daemon"]._running is True
    assert message_helpers is not None


def test_courier_processes_message(courier_instance, message_helpers):
    """Verify a message written to inbox is picked up by courier."""
    helpers = message_helpers

    # Send a message from agent-a to agent-b (file-only agent).
    msg_path = helpers.send_message(
        from_agent="agent-a",
        to_agent="team-lead",
        content="Smoke test message",
    )
    assert msg_path.exists()

    # Wait for courier to archive the message.
    archived = helpers.wait_for_archive("team-lead", timeout=5.0)
    assert len(archived) >= 1, "Expected at least 1 archived message for team-lead"
