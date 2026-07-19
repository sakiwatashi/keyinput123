"""A single-syllable, slot-replacement Bopomofo editor.

The important distinction from a sentence-oriented IME is that a tone does not
hard-commit the syllable. The user may still replace any phonetic component
until an explicit commit action is sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


INITIALS = frozenset("ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙ")
MEDIALS = frozenset("ㄧㄨㄩ")
RIMES = frozenset("ㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦ")
TONES = frozenset("ˉˊˇˋ˙")
SLOT_ORDER = ("initial", "medial", "rime", "tone")


class EventKind(Enum):
    UPDATED = auto()
    COMMITTED = auto()
    CLEARED = auto()
    BELL = auto()
    IGNORED = auto()


@dataclass(frozen=True)
class Event:
    kind: EventKind
    preedit: str = ""
    committed: str = ""
    reason: str = ""


Validator = Callable[[str], bool]


def slot_for(symbol: str) -> str | None:
    if symbol in INITIALS:
        return "initial"
    if symbol in MEDIALS:
        return "medial"
    if symbol in RIMES:
        return "rime"
    if symbol in TONES:
        return "tone"
    return None


class BopomofoEditor:
    """Edit one uncommitted syllable using replaceable component slots."""

    def __init__(self, validator: Validator | None = None) -> None:
        self._slots: dict[str, str] = {}
        self._edit_order: list[str] = []
        self._validator = validator

    @property
    def preedit(self) -> str:
        return "".join(self._slots.get(slot, "") for slot in SLOT_ORDER)

    @property
    def is_empty(self) -> bool:
        return not self._slots

    def input_symbol(self, symbol: str) -> Event:
        slot = slot_for(symbol)
        if slot is None:
            return Event(EventKind.BELL, self.preedit, reason="不是注音符號")

        candidate_slots = dict(self._slots)
        candidate_slots[slot] = symbol
        candidate = "".join(candidate_slots.get(name, "") for name in SLOT_ORDER)

        if self._validator is not None and not self._validator(candidate):
            return Event(EventKind.BELL, self.preedit, reason="這個音節沒有有效候選")

        self._slots = candidate_slots
        if slot in self._edit_order:
            self._edit_order.remove(slot)
        self._edit_order.append(slot)
        return Event(EventKind.UPDATED, self.preedit)

    def backspace(self) -> Event:
        if not self._edit_order:
            return Event(EventKind.BELL, reason="沒有可刪除的音符")
        slot = self._edit_order.pop()
        self._slots.pop(slot, None)
        return Event(EventKind.UPDATED, self.preedit)

    def clear(self) -> Event:
        self._slots.clear()
        self._edit_order.clear()
        return Event(EventKind.CLEARED)

    def commit(self, text: str | None = None) -> Event:
        if self.is_empty:
            return Event(EventKind.BELL, reason="沒有可確認的音節")
        committed = text if text is not None else self.preedit
        self.clear()
        return Event(EventKind.COMMITTED, committed=committed)
