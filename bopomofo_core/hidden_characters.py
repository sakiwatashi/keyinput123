"""Which candidate characters the user never wants to see.

Taiwan frequency alone cannot make this call. Measured on the bundled table,
"rare and useless" and "rare but wanted" overlap completely: 恣 is 5 and 祐 is
1, 孳 is 6 and 珮 is 7, while 昕 and 彤 sit at 0 alongside 眥 and 剚. No single
threshold separates them.

A hand-picked list alone does not work either. Hiding 孳 恣 磧 眥 剚 胔 from
ㄗˋ simply promoted 胾 扻 倳 牸 芓 絘 from further down the same reading, so
curating by hand turns into whack-a-mole.

Hence three parts, in order of authority:

    always_show        characters kept no matter what, for the 祐 case
    hidden             characters removed no matter what
    minimum_frequency  a floor; anything scoring below it goes. 0 disables it.

The floor does the bulk work and covers characters nobody has enumerated,
including those absent from the frequency table entirely. The two lists are
the user's corrections to it.

Hiding is not deleting: the bundled dictionary is third-party data and stays
untouched, so clearing the settings brings every character straight back.
"""

from __future__ import annotations

import json
import os

from .taiwan_frequency import TaiwanFrequency

CONFIG_NAME = "hidden-characters.json"

_FREQUENCY = TaiwanFrequency()


def _config_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", CONFIG_NAME)


class HiddenCharacters:
    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._loaded = False
        self._hidden: frozenset[str] = frozenset()
        self._always_show: frozenset[str] = frozenset()
        self._minimum_frequency = 0

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path if self._path is not None else _config_path()
        try:
            # utf-8-sig: the control panel is PowerShell and may write a BOM,
            # which json rejects. Reading it as plain utf-8 would make the
            # settings look absent with no error anywhere.
            with open(path, "r", encoding="utf-8-sig") as handle:
                raw = json.load(handle)
        except Exception:
            # Absent or damaged means nothing is hidden. A broken preference
            # must never make characters disappear.
            return
        if not isinstance(raw, dict):
            return
        self._hidden = self._character_set(raw.get("hidden"))
        self._always_show = self._character_set(raw.get("always_show"))
        floor = raw.get("minimum_frequency")
        if isinstance(floor, int) and floor > 0:
            self._minimum_frequency = floor

    @staticmethod
    def _character_set(value) -> frozenset[str]:
        if not isinstance(value, list):
            return frozenset()
        return frozenset(
            entry for entry in value if isinstance(entry, str) and len(entry) == 1
        )

    def is_hidden(self, character: str) -> bool:
        self._ensure_loaded()
        if len(character) != 1 or character in self._always_show:
            return False
        if character in self._hidden:
            return True
        if self._minimum_frequency <= 0:
            return False
        return _FREQUENCY.score(character) < self._minimum_frequency

    def filter(self, candidates: list[str]) -> list[str]:
        """Drop hidden characters, but never return nothing.

        A reading whose every candidate is hidden would leave the user unable
        to finish that syllable at all. Keeping the original list in that case
        makes an over-eager setting annoying rather than a trap.
        """
        self._ensure_loaded()
        if not self._hidden and self._minimum_frequency <= 0:
            return candidates
        kept = [
            candidate for candidate in candidates if not self.is_hidden(candidate)
        ]
        return kept if kept else candidates

    def reload(self) -> None:
        self._loaded = False
        self._hidden = frozenset()
        self._always_show = frozenset()
        self._minimum_frequency = 0


shared_hidden_characters = HiddenCharacters()
