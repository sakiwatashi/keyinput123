"""Conservative, offline correction of high-confidence Traditional Chinese typos."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_RULES = Path(__file__).with_name("data") / "common_typos.json"


@dataclass(frozen=True)
class AutocorrectRule:
    wrong: str
    correct: str
    source: str


@dataclass(frozen=True)
class Autocorrection:
    start: int
    wrong: str
    correct: str
    source: str


class Autocorrector:
    """Apply exact, same-length rules without touching protected characters."""

    def __init__(self, path: str | Path = DEFAULT_RULES) -> None:
        self.path = Path(path)
        self.rules: tuple[AutocorrectRule, ...] = ()
        self.sources: dict[str, dict[str, str]] = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            sources = raw.get("meta", {}).get("sources", [])
            if isinstance(sources, list):
                self.sources = {
                    str(source["id"]): {
                        str(key): str(value) for key, value in source.items()
                    }
                    for source in sources
                    if isinstance(source, dict) and source.get("id")
                }

            unique: dict[str, AutocorrectRule] = {}
            rows = raw.get("rules", [])
            if not isinstance(rows, list):
                return
            for row in rows:
                if not isinstance(row, dict):
                    continue
                wrong = row.get("wrong")
                correct = row.get("correct")
                source = row.get("source")
                if not all(isinstance(value, str) for value in (wrong, correct, source)):
                    continue
                # The first release deliberately keeps one character aligned
                # with one completed syllable. This makes user-selected spans
                # safe to protect and avoids surprising insertion/deletion.
                if not wrong or wrong == correct or len(wrong) != len(correct):
                    continue
                if source not in self.sources:
                    continue
                unique.setdefault(wrong, AutocorrectRule(wrong, correct, source))
            self.rules = tuple(
                sorted(unique.values(), key=lambda rule: (-len(rule.wrong), rule.wrong))
            )
        except (OSError, ValueError, TypeError, KeyError):
            # Autocorrection is optional. A missing or damaged rule file must
            # never stop the input method from starting.
            self.rules = ()
            self.sources = {}

    @property
    def rule_count(self) -> int:
        return len(self.rules)

    def correct(
        self, text: str, protected: Sequence[bool] | None = None
    ) -> tuple[str, list[Autocorrection]]:
        """Return corrected text and an audit trail of applied exact rules."""
        if protected is None:
            protected = (False,) * len(text)
        if len(protected) != len(text):
            raise ValueError("protected character mask must match text length")

        characters = list(text)
        changes: list[Autocorrection] = []
        index = 0
        while index < len(characters):
            current = "".join(characters)
            matched = False
            for rule in self.rules:
                end = index + len(rule.wrong)
                if end > len(characters) or current[index:end] != rule.wrong:
                    continue
                if any(protected[index:end]):
                    continue
                characters[index:end] = rule.correct
                changes.append(
                    Autocorrection(index, rule.wrong, rule.correct, rule.source)
                )
                index = end
                matched = True
                break
            if not matched:
                index += 1
        return "".join(characters), changes
