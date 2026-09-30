"""自動完成：你打過的句子，下次打到一半時提示後半段，按 Tab 接上。

記的是**送出的每一段中文**（連續、可打的注音跨度），連同每個字的讀音。讀音跟著存，
是因為接上去的字要能在組字區裡照常修改——沒有讀音就沒辦法再選字。

提示要夠有把握才出現：

* 至少打了 MIN_CONTEXT 個字當線索。只憑一個字，「我」後面接什麼都有可能，提示
  只會一直冒出來擋路。
* 同一段線索後面接過同一串字，累計 MIN_USES 次。一次跟隨手打的句子分不開。
  次數是跨句子加總的：「謝謝您的協助」出現在三句不同的話裡，就算三次。
* 提示延伸到大家都同意的地方為止。你打過「謝謝您的協助」兩次、「謝謝您的協助喔」
  一次，提示的是「您的協助」三個人都同意的那一段，不是其中任何一句的全文。

這裡**不影響選字排序**。它不碰 phrases.json、pins.json、word_usage.json，
只負責「要不要提示、提示什麼」；提示本身看得見，要不要接上由使用者按 Tab 決定。
所以它跟「自動送出不得悄悄教會個人詞庫」那條規矩不衝突——它教的東西從來不會
自己改掉畫面上的字。

獨立一個檔（completions.json），跟 usage.json 一樣：壞掉或不見只讓提示消失，
打字照常。內容是你實際打過的句子，跟 usage.json 同等敏感，不要上傳給別人。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .storage import load_json_object, save_json_object

CONFIG_NAME = "autocomplete.json"

# 至少要有幾個字當線索。見檔頭說明。
MIN_CONTEXT = 2
# 線索最長看幾個字。越長越準，但越少句子對得上；從長往短找，找到就停。
MAX_CONTEXT = 6
# 同一串後續要累計出現幾次才提示。跟 WORD_USE_CONFIDENCE 同一個理由：一次跟
# 隨手送出的句子分不開。
MIN_USES = 3
# 提示至少補幾個字。只補一個字省不到按鍵，還多一個提示框要看。
MIN_COMPLETION = 2
MAX_COMPLETION = 12

# 只記這個長度範圍內的跨度。太短的本身就是一個詞，詞網格已經處理得很好；
# 太長的通常是一次性的長段落，不會再打第二次。
MIN_RECORD_LENGTH = MIN_CONTEXT + MIN_COMPLETION
MAX_RECORD_LENGTH = 32

# 跟 usage_store 一樣緩衝寫入：fsync 加原子替換的成本隨檔案變大，每句話都寫
# 會拖慢打字。
FLUSH_EVERY = 20
MAX_ENTRIES = 3000
TRIM_TO = 2000


def default_config_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", CONFIG_NAME)


def autocomplete_enabled(config_path: str | None = None) -> bool:
    """**預設開啟**，只有明確寫 ``"enabled": false`` 才關。

    跟讀音改字（預設關閉）相反，理由也相反：讀音改字會自己改掉你打對的字，
    自動完成只是提示，不按 Tab 什麼都不會發生。

    檔案不存在、壞掉、缺欄位都當成預設（開啟）。在建構時讀一次，不在打字路徑上讀。
    """
    path = config_path if config_path is not None else default_config_path()
    try:
        # utf-8-sig：Windows PowerShell 寫的檔會帶 BOM，見 phonetic_preference.py。
        with open(path, "r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return True
    if not isinstance(value, dict) or "enabled" not in value:
        return True
    return bool(value["enabled"])


class CompletionStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        # 文字 → {"r": 每個字的讀音, "n": 次數, "last": 最後一次的時間}
        self._entries: dict[str, dict] = {}
        self._pending = 0
        if self.path is not None and self.path.exists():
            self.load()

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        entries = raw.get("entries", {}) if isinstance(raw, dict) else {}
        cleaned: dict[str, dict] = {}
        for text, value in entries.items() if isinstance(entries, dict) else ():
            # 什麼都容忍：統計檔壞掉絕不能讓輸入法起不來。
            if not isinstance(text, str) or not isinstance(value, dict):
                continue
            readings = value.get("r")
            if (
                not isinstance(readings, list)
                or len(readings) != len(text)
                or not all(isinstance(reading, str) and reading for reading in readings)
            ):
                continue
            try:
                count, last = int(value.get("n", 0)), int(value.get("last", 0))
            except (TypeError, ValueError):
                continue
            if count > 0:
                cleaned[text] = {"r": list(readings), "n": count, "last": last}
        self._entries = cleaned

    def record(self, readings: list[str], text: str) -> None:
        """數一次「送出了這段文字」。長度不在範圍內、讀音對不上字數就不記。"""
        if len(readings) != len(text):
            return
        if not MIN_RECORD_LENGTH <= len(text) <= MAX_RECORD_LENGTH:
            return
        entry = self._entries.get(text)
        if entry is None:
            entry = {"r": list(readings), "n": 0, "last": 0}
            self._entries[text] = entry
        else:
            # 同一段文字換了讀音（破音字），以最新的為準。
            entry["r"] = list(readings)
        entry["n"] += 1
        entry["last"] = int(time.time())
        self._pending += 1
        if self._pending >= FLUSH_EVERY:
            self.flush()

    def flush(self, force: bool = False) -> None:
        if self.path is None:
            return
        if self._pending == 0 and not force:
            return
        self._trim()
        save_json_object(self.path, {"version": 1, "entries": self._entries})
        self._pending = 0

    def suggest(
        self, readings: list[str], texts: list[str]
    ) -> tuple[str, list[str]] | None:
        """組字區結尾是 ``texts``（讀音 ``readings``）時，提示接下去的字。

        回傳 (要補上的文字, 每個字的讀音)，沒有夠把握的提示就回傳 None。
        線索從長往短找：長線索對得上的提示比短線索的更貼近你現在在打的這句。
        """
        if len(readings) != len(texts):
            return None
        longest = min(MAX_CONTEXT, len(texts))
        for width in range(longest, MIN_CONTEXT - 1, -1):
            found = self._suggest_after(readings[-width:], "".join(texts[-width:]))
            if found is not None:
                return found
        return None

    def _suggest_after(
        self, context_readings: list[str], context: str
    ) -> tuple[str, list[str]] | None:
        width = len(context)
        # 所有出現過這段線索的地方，後面接了什麼。讀音也要對得上：同字不同音
        # （「長大」與「長度」的長）是不同的線索。
        followers: list[tuple[str, list[str], int, int]] = []
        for text, entry in self._entries.items():
            start = text.find(context)
            while start != -1:
                end = start + width
                if end < len(text) and entry["r"][start:end] == context_readings:
                    followers.append(
                        (text[end:], entry["r"][end:], entry["n"], entry["last"])
                    )
                start = text.find(context, start + 1)
        if not followers:
            return None

        # 一次延伸一個字，只沿著累計次數夠多的那條路走。停在大家不再同意的地方。
        completion = ""
        completion_readings: list[str] = []
        while len(completion) < MAX_COMPLETION:
            position = len(completion)
            tally: dict[tuple[str, str], list[int]] = {}
            for rest, rest_readings, count, last in followers:
                if len(rest) <= position or not rest.startswith(completion):
                    continue
                key = (rest[position], rest_readings[position])
                score = tally.setdefault(key, [0, 0])
                score[0] += count
                score[1] = max(score[1], last)
            if not tally:
                break
            # 次數高的優先；同分看誰比較近用過，再同分就照字排，讓結果可重現。
            (character, reading), (count, _) = max(
                tally.items(), key=lambda item: (item[1][0], item[1][1], item[0])
            )
            if count < MIN_USES:
                break
            completion += character
            completion_readings.append(reading)

        if len(completion) < MIN_COMPLETION:
            return None
        return (completion, completion_readings)

    def _trim(self) -> None:
        if len(self._entries) <= MAX_ENTRIES:
            return
        ranked = sorted(
            self._entries.items(),
            key=lambda item: (item[1]["n"], item[1]["last"]),
            reverse=True,
        )
        self._entries = dict(ranked[:TRIM_TO])

    def __len__(self) -> int:
        return len(self._entries)
