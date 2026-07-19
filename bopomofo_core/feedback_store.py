"""Privacy-preserving local collection of explicit conversion corrections."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .storage import load_json_object, save_json_object


MAX_ENTRIES = 1_000


class FeedbackStore:
    """Store only differences the user explicitly corrected.

    Surrounding text, application names, and automatically accepted input are
    deliberately excluded. Nothing in this class performs network access.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._entries: list[dict[str, object]] = []
        if self.path is not None and self.path.exists():
            self.load()

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        entries = raw.get("entries", [])
        if not isinstance(entries, list):
            self._entries = []
            return
        self._entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("id"), str)
            and isinstance(entry.get("readings"), list)
            and isinstance(entry.get("converted"), str)
            and isinstance(entry.get("expected"), str)
        ][-MAX_ENTRIES:]

    def save(self) -> None:
        if self.path is not None:
            save_json_object(
                self.path, {"version": 1, "entries": self._entries}
            )

    def record(
        self, readings: list[str], converted: str, expected: str
    ) -> None:
        if (
            not readings
            or converted == expected
            or len(converted) != len(expected)
            or len(readings) != len(expected)
        ):
            return
        normalized_readings = [str(reading) for reading in readings]
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for entry in self._entries:
            if (
                entry["readings"] == normalized_readings
                and entry["converted"] == converted
                and entry["expected"] == expected
            ):
                entry["count"] = int(entry.get("count", 1)) + 1
                entry["last_seen"] = timestamp
                self.save()
                return
        self._entries.append(
            {
                "id": uuid4().hex,
                "readings": normalized_readings,
                "converted": converted,
                "expected": expected,
                "count": 1,
                "last_seen": timestamp,
            }
        )
        self._entries = self._entries[-MAX_ENTRIES:]
        self.save()

    def entries(self) -> list[dict[str, object]]:
        return [dict(entry) for entry in self._entries]

    def remove(self, identifiers: set[str]) -> None:
        if not identifiers:
            return
        self._entries = [
            entry for entry in self._entries if entry["id"] not in identifiers
        ]
        self.save()

    def clear(self) -> None:
        self._entries = []
        self.save()
