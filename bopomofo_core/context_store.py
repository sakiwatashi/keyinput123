"""Which word the user chose for a reading *after a particular character*.

phrases.json answers "what did this reading become", with no notion of where.
That is why one learned pair can wreck an unrelated sentence: choosing 程式
once for ㄔㄥˊ ㄕˋ turns 這座城市很美麗 into 這座程式很美麗, because the
personal entry outranks every bundled option for that span no matter what sits
next to it.

The fix other input methods use is context. 座 → 城市 and 寫 → 程式 are both
common; 座 → 程式 and 寫 → 城市 are not. One character of left context is
enough to separate them, and it is the cheapest context there is -- the decoder
already knows the text to the left of every span it considers.

Stored separately from phrases.json on purpose, following usage.json: that file
holds the user's only irreplaceable data, and changing its format would put it
behind a migration. A missing or damaged contexts.json costs nothing but this
refinement -- typing falls back to exactly today's behaviour.

Shape on disk, grouped by reading so a human can read it:

    {"ㄔㄥˊ ㄕˋ": {"寫": "程式", "座": "城市"}}
"""

from __future__ import annotations

from pathlib import Path

from .storage import load_json_object, save_json_object

# Contexts are cheap to record and there is one per reading per neighbour, so
# the total grows faster than phrases.json. The cap is on readings rather than
# pairs because a reading with many recorded neighbours is exactly the
# ambiguous case this exists to serve.
MAX_READINGS = 20_000
MAX_CONTEXTS_PER_READING = 16


class ContextStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._entries: dict[str, dict[str, str]] = {}
        if self.path is not None and self.path.exists():
            self.load()

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        cleaned: dict[str, dict[str, str]] = {}
        for reading, contexts in raw.items():
            if not isinstance(reading, str) or not isinstance(contexts, dict):
                continue
            pairs = {
                str(context): str(phrase)
                for context, phrase in contexts.items()
                if isinstance(context, str) and len(context) == 1 and phrase
            }
            if pairs:
                cleaned[reading] = pairs
        self._entries = cleaned

    def save(self) -> None:
        if self.path is None:
            return
        save_json_object(self.path, self._entries)

    def learn(self, readings: list[str], phrase: str, context: str) -> None:
        """Record that ``phrase`` followed ``context`` for these readings.

        A context of anything but exactly one character is ignored rather than
        stored under a made-up key: a span at the very start of a composition
        genuinely has no left neighbour, and inventing one would file every
        sentence-initial choice under the same bucket.
        """
        if len(readings) != len(phrase) or len(context) != 1:
            return
        key = self._key(readings)
        contexts = self._entries.setdefault(key, {})
        if contexts.get(context) == phrase:
            return
        # Re-insert so the newest choice sits last; the trim below drops from
        # the front, which makes it least-recently-chosen rather than arbitrary.
        contexts.pop(context, None)
        contexts[context] = phrase
        while len(contexts) > MAX_CONTEXTS_PER_READING:
            contexts.pop(next(iter(contexts)))
        while len(self._entries) > MAX_READINGS:
            self._entries.pop(next(iter(self._entries)))
        self.save()

    def lookup(self, readings: list[str], context: str) -> str:
        """The word chosen for these readings after this character, if any."""
        if len(context) != 1:
            return ""
        return self._entries.get(self._key(readings), {}).get(context, "")

    def contexts_for(self, readings: list[str]) -> dict[str, str]:
        return dict(self._entries.get(self._key(readings), {}))

    def __len__(self) -> int:
        return len(self._entries)
