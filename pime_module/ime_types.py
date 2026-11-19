#! python3
"""組字區的資料型別。主模組、詞語排序、自動完成都用得到，所以獨立一個檔，
避免模組之間互相匯入。"""

from __future__ import annotations

from dataclasses import dataclass

from .bopomofo_core.state import INITIALS, MEDIALS, RIMES, TONES

# 原始注音符號本身（ㄅ、ˊ）。它們是可打的讀音，但不是中文字。
BOPOMOFO_TEXT = INITIALS | MEDIALS | RIMES | TONES


@dataclass
class BufferedSyllable:
    reading: str
    candidates: list[str]
    selected: int = 0
    locked: bool = False
    # True only when the user explicitly chose this segment's text. Commit
    # uses it to tell a hand-corrected composition apart from the engine's
    # own guesses, which must never teach the personal lexicon.
    user_corrected: bool = False
    # 鎖住的理由是詞網格自動比對到個人詞，而不是使用者在這次組字裡親手選的。
    # 這種鎖只擋錯字修正與整句候選，不擋詞網格本身：每多打一個字都要重新
    # 評估，否則學過的「下一」一旦鎖住，後面的ㄅㄨˋ再也接不成「下一步」，
    # 只能落單照單字預設變成「不」——實測「下一步吧」因此打成「下一不吧」。
    auto_locked: bool = False

    @property
    def text(self) -> str:
        return self.candidates[self.selected]


@dataclass(frozen=True)
class CandidateChoice:
    """One displayed candidate and the segment range it replaces."""

    text: str
    start: int
    end: int

    @property
    def width(self) -> int:
        return self.end - self.start
