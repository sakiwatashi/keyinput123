"""Pronunciation-aware Traditional Chinese phrase lookup.

The bundled corpus indexes phrases by their complete Bopomofo readings.  It
is deliberately separate from the text-only frequency indexes: a common word
must not be borrowed by an unrelated alternate pronunciation.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


DEFAULT_INDEX = Path(__file__).with_name("data") / "reading_phrases.json.gz"


class ReadingPhraseLexicon:
    def __init__(self, path: str | Path = DEFAULT_INDEX) -> None:
        self.path = Path(path)
        self.entry_count = 0
        self._entries: dict[str, list[list[object]]] = {}
        if not self.path.exists():
            return
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as stream:
                raw = json.load(stream)
            if not isinstance(raw, dict):
                return
            meta = raw.get("meta", {})
            entries = raw.get("entries", {})
            if not isinstance(meta, dict) or not isinstance(entries, dict):
                return
            self.entry_count = int(meta.get("entry_count", 0))
            self._entries = {
                str(key): rows
                for key, rows in entries.items()
                if isinstance(rows, list)
            }
        except (OSError, ValueError, TypeError):
            self.entry_count = 0
            self._entries = {}

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def candidates(self, readings: list[str], limit: int = 20) -> list[str]:
        if not readings or limit <= 0:
            return []
        results: list[str] = []
        for row in self._entries.get(self._key(readings), []):
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase = row[0]
            if (
                isinstance(phrase, str)
                and len(phrase) == len(readings)
                and phrase not in results
            ):
                results.append(phrase)
                if len(results) >= limit:
                    break
        return results

    def weight(self, readings: list[str], phrase: str) -> int:
        if len(phrase) != len(readings):
            return 0
        for row in self._entries.get(self._key(readings), []):
            if not isinstance(row, list) or len(row) != 2 or row[0] != phrase:
                continue
            try:
                return max(0, int(row[1]))
            except (TypeError, ValueError):
                return 0
        return 0

