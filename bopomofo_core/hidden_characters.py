"""Which candidate characters the user never wants to see.

Taiwan frequency alone cannot make this call. Measured on the bundled table,
"rare and useless" and "rare but wanted" overlap completely: 恣 is 5 and 祐 is
1, 孳 is 6 and 珮 is 7, while 昕 and 彤 sit at 0 alongside 眥 and 剚. No single
threshold separates them.

A hand-picked list alone does not work either. Hiding 孳 恣 磧 眥 剚 胔 from
ㄗˋ simply promoted 胾 扻 倳 牸 芓 絘 from further down the same reading, so
curating by hand turns into whack-a-mole.

The frequency table is worse than "imprecise" -- it is from a different
register. Its source is the 1996 「85年常用語詞調查報告」, a survey of formal
written Chinese, so everyday spoken characters score near nothing: 嗯 is 7,
欸 is 1, 齁 and 唷 are 0, against 的 at 39632. Characters that exist only
inside set phrases score the same way: 囫 圇 釜 are all 0.

So a bare threshold cannot be the rule. Two things rescue it, measured:

  * A character that appears anywhere in the bundled phrase lexicon is a
    character somebody needs. 囫 圇 釜 徇 斟 竿 嗯 are all in there. At a
    threshold of 7, 1482 characters fall below the line but 1212 of them
    (82%) appear in a real phrase, leaving 270 genuinely hidable. At 20 the
    remainder is 290 -- the hidable set converges regardless of threshold,
    which is what a real "obscure" set should do.
  * Spoken particles are the gap no dictionary fills, since no phrase
    contains them. They are listed here.

Hence, in order of authority:

    always_show        characters kept no matter what, for the 祐 case
    hidden             characters removed no matter what
    COLLOQUIAL_KEEP    spoken particles the corpus and dictionaries both miss
    the phrase lexicon characters used by any bundled phrase
    minimum_frequency  a floor for what is left. 0 disables filtering.

Hiding is not deleting: the bundled dictionary is third-party data and stays
untouched, so clearing the settings brings every character straight back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .taiwan_frequency import TaiwanFrequency

CONFIG_NAME = "hidden-characters.json"

# 85年常用語詞調查報告 is written Chinese, and no phrase dictionary lists a
# bare particle, so these fall through both defences while being among the
# most typed characters in a chat window.
COLLOQUIAL_KEEP = frozenset("嗯喔啦欸齁嘛耶唄唷噢咧哦嘿吼囉呦嗨欽")

_FREQUENCY = TaiwanFrequency()
_PHRASE_INDEX = Path(__file__).with_name("data") / "high_frequency_phrases.json"
_lexicon_characters: frozenset[str] | None = None


def lexicon_characters() -> frozenset[str]:
    """Every character used by any bundled phrase.

    Built on first use and only when filtering is switched on: reading and
    walking the 2 MB index costs about 60 ms, which is not worth paying for
    users who never enable the floor.
    """
    global _lexicon_characters
    if _lexicon_characters is not None:
        return _lexicon_characters

    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, str):
            found.update(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        with open(_PHRASE_INDEX, "r", encoding="utf-8") as handle:
            walk(json.load(handle).get("buckets", {}))
    except Exception:
        # A missing or damaged index must not start hiding characters that
        # would otherwise have been protected, so fail towards keeping them:
        # an empty set here only means the floor applies unaided, which is the
        # previous behaviour rather than something worse.
        pass

    _lexicon_characters = frozenset(
        character for character in found if "一" <= character <= "鿿"
    )
    return _lexicon_characters


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

    def is_hidden(self, character: str, floor: int | None = None) -> bool:
        """Whether this character is filtered out.

        ``floor`` overrides the stored threshold. The control panel needs that
        to preview a value the user has typed but not saved yet, and the
        preview has to come from this rule rather than a second copy of it.
        """
        self._ensure_loaded()
        if len(character) != 1 or character in self._always_show:
            return False
        if character in self._hidden:
            return True
        minimum = self._minimum_frequency if floor is None else floor
        if minimum <= 0:
            return False
        # A spoken particle, or a character any bundled phrase uses, survives
        # the floor. Without this a threshold of 7 took 嗯 (7), 囫 圇 釜 (0)
        # and every other set-phrase character with it -- the frequency table
        # is a 1996 survey of written Chinese and simply does not see them.
        if character in COLLOQUIAL_KEEP:
            return False
        if character in lexicon_characters():
            return False
        return _FREQUENCY.score(character) < minimum

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
