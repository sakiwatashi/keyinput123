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

    def score(self, character: str) -> int:
        """This character's Taiwan frequency, 0 when the table does not list it.

        Absent and genuinely-zero are deliberately the same answer: callers
        that use this as a floor want both treated as "not common".
        """
        return self._characters.get(character, 0)

    def rank_characters(
        self, candidates: list[str], *, preserve_first: bool = False
    ) -> list[str]:
        """Rank by Taiwan frequency without losing reading-specific evidence.

        ``candidates`` normally comes from a pronunciation-aware dictionary.
        Its first entry is therefore stronger evidence than a character's
        global frequency, which cannot distinguish polyphonic readings such
        as 員 (usually ㄩㄢˊ, but also present under ㄩㄣˋ). Callers may keep
        that dictionary default while frequency-sorting the remaining tail.
        """
        unique = list(dict.fromkeys(candidates))
        if not unique:
            return []
        positions = {candidate: index for index, candidate in enumerate(candidates)}
        ranked = sorted(
            unique,
            key=lambda candidate: (
                -self._characters.get(candidate, 0),
                positions[candidate],
            ),
        )
        if not preserve_first:
            return ranked
        first = unique[0]
        return [first] + [candidate for candidate in ranked if candidate != first]

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

    def contains_phrase(self, phrase: str) -> bool:
        """Return whether the official word table contains the whole phrase."""
        if len(phrase) < 2:
            return False
        bucket = self._buckets.get(str(len(phrase)), {})
        if not isinstance(bucket, dict):
            return False
        rows = bucket.get(phrase[0], [])
        return isinstance(rows, list) and any(
            isinstance(row, list) and len(row) == 2 and row[0] == phrase
            for row in rows
        )
