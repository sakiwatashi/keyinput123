"""Persistent personal multi-syllable phrase index."""

from __future__ import annotations

from pathlib import Path

from .storage import load_json_object, save_json_object


MIN_PHRASE_LENGTH = 2
MAX_PHRASE_LENGTH = 12
MAX_ENTRIES = 20_000


class PhraseStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._entries: dict[str, str] = {}
        if self.path is not None and self.path.exists():
            self.load()

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        self._entries = {
            str(readings): str(phrase) for readings, phrase in raw.items()
        }

    def save(self) -> None:
        if self.path is None:
            return
        save_json_object(self.path, self._entries)

    def learn(self, readings: list[str], phrase: str) -> None:
        """Learn every useful n-gram from one user-approved composition."""
        if len(readings) != len(phrase):
            return
        changed = False
        max_width = min(MAX_PHRASE_LENGTH, len(readings))
        for width in range(MIN_PHRASE_LENGTH, max_width + 1):
            for start in range(0, len(readings) - width + 1):
                key = self._key(readings[start : start + width])
                value = phrase[start : start + width]
                if self._entries.get(key) == value:
                    continue
                self._entries.pop(key, None)
                self._entries[key] = value
                changed = True
        while len(self._entries) > MAX_ENTRIES:
            self._entries.pop(next(iter(self._entries)))
            changed = True
        if changed:
            self.save()

    def best_suffix(self, readings: list[str]) -> tuple[int, str]:
        max_width = min(MAX_PHRASE_LENGTH, len(readings))
        for width in range(max_width, MIN_PHRASE_LENGTH - 1, -1):
            phrase = self._entries.get(self._key(readings[-width:]))
            if phrase is not None:
                return width, phrase
        return 0, ""
