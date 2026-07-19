"""Persistent exact-reading candidate priorities."""

from __future__ import annotations

import json
from pathlib import Path


class PinnedStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._entries: dict[str, list[str]] = {}
        if self.path is not None and self.path.exists():
            self.load()

    def load(self) -> None:
        if self.path is None:
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._entries = {
            str(reading): [str(phrase) for phrase in phrases]
            for reading, phrases in raw.items()
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def phrases_for(self, reading: str) -> list[str]:
        return list(self._entries.get(reading, ()))

    def pin(self, reading: str, phrase: str) -> None:
        phrases = self._entries.setdefault(reading, [])
        if phrase in phrases:
            phrases.remove(phrase)
        phrases.insert(0, phrase)
        self.save()

    def unpin(self, reading: str, phrase: str) -> None:
        phrases = self._entries.get(reading)
        if not phrases:
            return
        if phrase in phrases:
            phrases.remove(phrase)
        if not phrases:
            self._entries.pop(reading, None)
        self.save()
