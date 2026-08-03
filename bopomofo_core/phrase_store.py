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

    def learn(
        self,
        readings: list[str],
        phrase: str,
        extra_spans: list[tuple[int, int]] | None = None,
    ) -> None:
        """Learn this composition, plus only the spans the caller names.

        This used to learn every substring of width 2..12 at every position.
        One twelve-character sentence therefore produced about 66 entries, and
        almost all of them were fragments straddling word boundaries that
        nobody would ever type on purpose. A real user's store reached 6912
        entries and 477 KB, with roughly half the short entries being
        substrings of longer ones.

        The caller knows which parts were actually chosen or corrected --
        that is what deserves to be remembered on its own. Everything else is
        recoverable from the full span.
        """
        if len(readings) != len(phrase):
            return

        spans = [(0, len(readings))]
        for start, end in extra_spans or ():
            if 0 <= start < end <= len(readings) and (start, end) != (0, len(readings)):
                spans.append((start, end))

        changed = False
        for start, end in spans:
            width = end - start
            if not MIN_PHRASE_LENGTH <= width <= MAX_PHRASE_LENGTH:
                continue
            key = self._key(readings[start:end])
            value = phrase[start:end]
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

    def prune_redundant(self) -> int:
        """Drop entries fully contained in a longer entry. Returns the count.

        Written to clean up stores already bloated by the old learn(). An entry
        is redundant when both its readings and its text appear, aligned, inside
        a longer stored entry: typing that longer reading still produces it, so
        the short copy only crowds the candidate list.
        """
        by_key = {key: (key.split(" "), value) for key, value in self._entries.items()}
        longer = sorted(by_key.items(), key=lambda item: -len(item[1][0]))

        redundant = []
        for key, (readings, value) in by_key.items():
            for other_key, (other_readings, other_value) in longer:
                if other_key == key or len(other_readings) <= len(readings):
                    continue
                for start in range(len(other_readings) - len(readings) + 1):
                    end = start + len(readings)
                    if (
                        other_readings[start:end] == readings
                        and other_value[start:end] == value
                    ):
                        redundant.append(key)
                        break
                else:
                    continue
                break

        for key in redundant:
            self._entries.pop(key, None)
        if redundant:
            self.save()
        return len(redundant)

    def best_suffix(self, readings: list[str]) -> tuple[int, str]:
        max_width = min(MAX_PHRASE_LENGTH, len(readings))
        for width in range(max_width, MIN_PHRASE_LENGTH - 1, -1):
            phrase = self._entries.get(self._key(readings[-width:]))
            if phrase is not None:
                return width, phrase
        return 0, ""

    def exact(self, readings: list[str]) -> str:
        """Return the personal phrase for exactly this reading span."""
        if not MIN_PHRASE_LENGTH <= len(readings) <= MAX_PHRASE_LENGTH:
            return ""
        return self._entries.get(self._key(readings), "")
