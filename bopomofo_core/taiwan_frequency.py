"""Read-only official Taiwan character and word frequency rankings."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_INDEX = Path(__file__).with_name("data") / "taiwan_frequency.json"


class TaiwanFrequency:
    def __init__(self, path: str | Path = DEFAULT_INDEX) -> None:
        self.path = Path(path)
        self.character_count = 0
        self.phrase_count = 0
        self._characters: dict[str, int] = {}
        self._buckets: dict[str, dict[str, list[list[object]]]] = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            meta = raw.get("meta", {})
            characters = raw.get("characters", {})
            buckets = raw.get("buckets", {})
            if not isinstance(meta, dict) or not isinstance(characters, dict):
                return
            if not isinstance(buckets, dict):
                return
            self.character_count = int(meta.get("character_count", 0))
            self.phrase_count = int(meta.get("phrase_count", 0))
            self._characters = {
                str(character): int(weight)
                for character, weight in characters.items()
            }
            self._buckets = buckets
        except (OSError, ValueError, TypeError):
            self.character_count = 0
            self.phrase_count = 0
            self._characters = {}
            self._buckets = {}

    def rank_characters(self, candidates: list[str]) -> list[str]:
        """Rank known characters by Taiwan frequency, preserving unknown order."""
        positions = {candidate: index for index, candidate in enumerate(candidates)}
        return sorted(
            dict.fromkeys(candidates),
            key=lambda candidate: (
                -self._characters.get(candidate, 0),
                positions[candidate],
            ),
        )

    def phrase_candidates(
        self, candidate_columns: list[list[str]], limit: int = 20
    ) -> list[str]:
        if len(candidate_columns) < 2 or limit <= 0:
            return []
        bucket = self._buckets.get(str(len(candidate_columns)), {})
        if not isinstance(bucket, dict):
            return []
        allowed = [set(column) for column in candidate_columns]
        ranked: dict[str, int] = {}
        for first_character in candidate_columns[0]:
            rows = bucket.get(first_character, [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, list) or len(row) != 2:
                    continue
                phrase, weight = row
                if not isinstance(phrase, str) or len(phrase) != len(allowed):
                    continue
                if all(char in column for char, column in zip(phrase, allowed)):
                    try:
                        ranked[phrase] = max(int(weight), ranked.get(phrase, 0))
                    except (TypeError, ValueError):
                        continue
        return [
            phrase
            for phrase, _ in sorted(
                ranked.items(), key=lambda item: (-item[1], item[0])
            )[:limit]
        ]
