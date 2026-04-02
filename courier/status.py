"""Per-message delivery status tracking for the soul courier."""
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("soul-courier.status")

STATUS_QUEUED = "queued"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_DLQ = "dlq"


class StatusStore:
    """Tracks per-message delivery status on disk.

    Stores one JSON file per agent at {status_dir}/{agent}.json.
    Each file is a list of entry dicts with keys:
        file, status, sender, detail, created_at, updated_at

    Atomic writes (write-to-tmp + rename) prevent corruption on crash.
    """

    def __init__(self, status_dir: Path):
        self._dir = status_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        agent: str,
        msg_file: Path,
        status: str,
        sender: str = "",
        detail: str = "",
    ) -> None:
        """Record or update the delivery status of a message.

        If the file has been seen before, the existing entry is updated
        in-place (status + updated_at + detail). Otherwise a new entry
        is appended.
        """
        entries = self._load(agent)
        fname = msg_file.name
        now = datetime.now(timezone.utc).isoformat()
        for entry in entries:
            if entry["file"] == fname:
                entry["status"] = status
                entry["updated_at"] = now
                if detail:
                    entry["detail"] = detail
                break
        else:
            entries.append(
                {
                    "file": fname,
                    "status": status,
                    "sender": sender,
                    "detail": detail,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        self._save(agent, entries)

    def get_agent_status(self, agent: str) -> list[dict]:
        """Return all status entries for an agent (oldest first)."""
        return self._load(agent)

    def get_all(self) -> dict[str, list[dict]]:
        """Return status entries for every agent that has data."""
        result: dict[str, list[dict]] = {}
        for f in self._dir.glob("*.json"):
            agent = f.stem
            entries = self._load(agent)
            if entries:
                result[agent] = entries
        return result

    def get_summary(self, agent: str) -> dict[str, int]:
        """Return counts keyed by status value for a given agent."""
        entries = self._load(agent)
        summary: dict[str, int] = {}
        for entry in entries:
            s = entry.get("status", "unknown")
            summary[s] = summary.get(s, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, agent: str) -> list[dict]:
        f = self._dir / f"{agent}.json"
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            log.warning("Corrupt status file for %s — resetting", agent)
        return []

    def _save(self, agent: str, entries: list[dict]) -> None:
        f = self._dir / f"{agent}.json"
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self._dir, suffix=".tmp", delete=False
            ) as tmp:
                json.dump(entries, tmp, indent=2)
                tmp_path = Path(tmp.name)
            tmp_path.rename(f)
        except Exception:
            log.exception("Failed to save status for %s", agent)
