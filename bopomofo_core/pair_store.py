"""你打字時哪兩個字常連在一起。整句選字拿它判斷上下文。

詞庫只知道每個詞本身多常見，不知道它前後接什麼，所以「現在是用一個」會變成
「現在適用一個」、「是能」變成「勢能」——「適用」「勢能」都是詞，「是用」「是能」
不是，而詞庫沒有辦法知道「在」後面你幾乎都接「是」。你自己送出過的文字知道。

記的是**送出的文字**裡每一對相鄰的漢字，跟 word_usage.json 同一個理由：修正只在
出錯時發生、量太少；送出的量夠大，偶爾夾帶的錯字會被沖淡。這不是單字或詞的
「優先」——它只替詞網格裡的每一種切法加一點分，詞頻與讀音仍然是主體。

獨立一個檔（pairs.json）：壞掉或不見只讓選字退回沒有上下文的樣子。內容等同你打
過的句子被拆成兩字一組，跟 usage.json 同等敏感，不要上傳給別人。
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Iterable, Tuple

from .storage import load_json_object, save_json_object

# 每一對「你打過幾次」換算成多少分，單位跟詞頻的 log 相同。
#
# 以使用者 1068 句確認過的句子依序重打、只用先前打過的句子來學，數手動選字次數：
# 0（不用）879、1 842、2 823、4 806、8 806。4 之後不再進步，取 4：同樣的效果下
# 越小越不會讓一個學過的字組壓過詞庫。
STRENGTH = 4.0

# 跟 usage_store 一樣緩衝寫入，fsync 加原子替換的成本不能加在每一句話後面。
FLUSH_EVERY = 20
MAX_PAIRS = 60_000
TRIM_TO = 45_000


def _is_han(character: str) -> bool:
    """只記漢字之間的相鄰。標點、英文、注音符號兩邊不構成上下文。"""
    code = ord(character)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x3134F
    )


class PairStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._pairs: dict[str, int] = {}
        self._pending = 0
        if self.path is not None and self.path.exists():
            self.load()

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        pairs = raw.get("pairs", {}) if isinstance(raw, dict) else {}
        cleaned: dict[str, int] = {}
        for pair, count in pairs.items() if isinstance(pairs, dict) else ():
            # 什麼都容忍：統計檔壞掉絕不能讓輸入法起不來。
            if not isinstance(pair, str) or len(pair) != 2:
                continue
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                cleaned[pair] = count
        self._pairs = cleaned

    def record(self, text: str, times: int = 1) -> None:
        """數一次「送出了這段文字」裡的每一對相鄰漢字。"""
        added = False
        for left, right in zip(text, text[1:]):
            if _is_han(left) and _is_han(right):
                self._pairs[left + right] = self._pairs.get(left + right, 0) + times
                added = True
        if added:
            self._pending += 1
            if self._pending >= FLUSH_EVERY:
                self.flush()

    def bootstrap(self, texts: Iterable[Tuple[str, int]]) -> None:
        """第一次啟動時用既有的送出紀錄（usage.json）預先學一輪，不必從零累積。"""
        for text, count in texts:
            if count > 0:
                self.record(text, count)
        self.flush(force=True)

    def count(self, pair: str) -> int:
        return self._pairs.get(pair, 0)

    def bonus(self, left: str, text: str) -> float:
        """``text`` 接在 ``left`` 後面時，你的習慣替它加多少分。

        包含跨過切分邊界的那一對（left 的最後一字接 text 的第一字）：「在｜是」
        就是那一對，詞網格每一段都各自只看得到自己裡面的字。
        """
        chain = (left[-1:] + text) if left else text
        total = 0.0
        for a, b in zip(chain, chain[1:]):
            count = self._pairs.get(a + b)
            if count:
                total += math.log1p(count)
        return STRENGTH * total

    def flush(self, force: bool = False) -> None:
        if self.path is None:
            return
        if self._pending == 0 and not force:
            return
        self._trim()
        save_json_object(
            self.path, {"version": 1, "updated": int(time.time()), "pairs": self._pairs}
        )
        self._pending = 0

    def _trim(self) -> None:
        if len(self._pairs) <= MAX_PAIRS:
            return
        # 留下次數最高的。很少出現的一對本來就加不了多少分。
        ranked = sorted(self._pairs.items(), key=lambda item: item[1], reverse=True)
        self._pairs = dict(ranked[:TRIM_TO])

    def __len__(self) -> int:
        return len(self._pairs)
