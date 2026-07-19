"""Read-only lookup for the bundled high-frequency phrase index."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_INDEX = Path(__file__).with_name("data") / "high_frequency_phrases.json"


class FrequencyLexicon:
    def __init__(self, path: str | Path = DEFAULT_INDEX) -> None:
        self.path = Path(path)
        self.entry_count = 0
        self._buckets: dict[str, dict[str, list[list[object]]]] = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            self.entry_count = int(raw.get("meta", {}).get("entry_count", 0))
            buckets = raw.get("buckets", {})
            if isinstance(buckets, dict):
                self._buckets = buckets
        except (OSError, ValueError, TypeError):
            # The base libchewing dictionary remains usable if an optional
            # expanded index is missing or damaged.
            self.entry_count = 0
            self._buckets = {}

    def candidates(
        self, candidate_columns: list[list[str]], limit: int = 12
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
                if all(character in column for character, column in zip(phrase, allowed)):
                    try:
                        numeric_weight = int(weight)
                    except (TypeError, ValueError):
                        continue
                    ranked[phrase] = max(numeric_weight, ranked.get(phrase, 0))

        return [
            phrase
            for phrase, _ in sorted(
                ranked.items(), key=lambda row: (-row[1], row[0])
            )[:limit]
        ]
