"""How often each committed string actually gets used.

phrases.json records *what* was learned, never *how often*, so the control
panel could list entries but not rank them. Counting therefore needs new data.

It lives in its own file on purpose. phrases.json holds the user's only
irreplaceable data, and changing its format would put that behind a migration;
a separate file means a corrupt or missing usage.json costs nothing but the
statistics -- typing keeps working exactly as before.

Writes are buffered. save_json_object does an fsync plus an atomic replace,
and doing that on every commit is precisely the mistake the keystroke trace
made: it wrote on every key and quietly grew to 742 KB while slowing typing.
"""

from __future__ import annotations

import time
from pathlib import Path

from .storage import load_json_object, save_json_object

# Flush after this many recorded commits. Small enough that a crash loses
# almost nothing, large enough that typing never waits on an fsync.
FLUSH_EVERY = 20

# Upper bound on tracked entries. Every distinct committed string counts, so
# without a cap this grows for as long as the user types. When it is reached
# the least-used entries go first, and ties break on the older last-used time.
MAX_ENTRIES = 4000
TRIM_TO = 3000


class UsageStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._counts: dict[str, dict[str, int]] = {}
        self._pending = 0
        if self.path is not None and self.path.exists():
            self.load()

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        entries = raw.get("counts", raw) if isinstance(raw, dict) else {}
        cleaned: dict[str, dict[str, int]] = {}
        for text, value in entries.items():
            if not isinstance(text, str) or not text:
                continue
            # Tolerate anything: a damaged statistics file must never stop the
            # input method from starting.
            if isinstance(value, dict):
                count = value.get("n", 0)
                last = value.get("last", 0)
            else:
                count, last = value, 0
            try:
                cleaned[text] = {"n": int(count), "last": int(last)}
            except (TypeError, ValueError):
                continue
        self._counts = cleaned

    def record(self, text: str) -> None:
        """Count one committed string. Single characters count too."""
        if not text:
            return
        entry = self._counts.get(text)
        if entry is None:
            entry = {"n": 0, "last": 0}
            self._counts[text] = entry
        entry["n"] += 1
        entry["last"] = int(time.time())
        self._pending += 1
        if self._pending >= FLUSH_EVERY:
            self.flush()

    def flush(self, force: bool = False) -> None:
        if self.path is None:
            return
        if self._pending == 0 and not force:
            return
        self._trim()
        save_json_object(self.path, {"version": 1, "counts": self._counts})
        self._pending = 0

    def _trim(self) -> None:
        if len(self._counts) <= MAX_ENTRIES:
            return
        ranked = sorted(
            self._counts.items(),
            key=lambda item: (item[1]["n"], item[1]["last"]),
            reverse=True,
        )
        self._counts = dict(ranked[:TRIM_TO])

    # ---- queries used by the control panel --------------------------------

    def by_length(self) -> dict[int, int]:
        """How many *distinct* strings of each length have been used."""
        result: dict[int, int] = {}
        for text in self._counts:
            result[len(text)] = result.get(len(text), 0) + 1
        return dict(sorted(result.items()))

    def totals_by_length(self) -> dict[int, int]:
        """How many *commits* of each length -- the volume, not the variety."""
        result: dict[int, int] = {}
        for text, entry in self._counts.items():
            result[len(text)] = result.get(len(text), 0) + entry["n"]
        return dict(sorted(result.items()))

    def most_used(self, limit: int = 20, length: int | None = None) -> list[dict]:
        items = [
            {"text": text, "count": entry["n"], "last": entry["last"]}
            for text, entry in self._counts.items()
            if length is None or len(text) == length
        ]
        items.sort(key=lambda item: (-item["count"], item["text"]))
        return items[:limit]

    def stale(self, limit: int = 20) -> list[dict]:
        """Least recently used first -- the honest basis for a cleanup."""
        items = [
            {"text": text, "count": entry["n"], "last": entry["last"]}
            for text, entry in self._counts.items()
        ]
        items.sort(key=lambda item: (item["last"], item["count"]))
        return items[:limit]

    def __len__(self) -> int:
        return len(self._counts)
