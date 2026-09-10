"""你自己的詞頻表。

phrases.json 是詞層級的（key 就是完整讀音串），但它沒有次數——用過五百次的詞和
誤學一次的詞，在排序上權威完全相同。「部要」「下一不」「編寫城市」就是這樣長期
壓過內建詞庫的。

字的層級救不了這件事：同一個讀音下的常用字太多，而且情況各不相同。「不」和「步」
當成字是無解的歧義，當成詞（「不要」／「下一步」）根本沒有歧義可言——讀音串不同，
不會互相干擾。所以計數要記在詞上。

記的是**送出時詞網格實際採用的每一個詞**，不是修正紀錄。修正只在出錯時發生，量太
少（實測 482 筆裡只有 93 筆是詞）；送出的量夠大，偶爾夾帶的錯字會被沖淡。

獨立一個檔，跟 usage.json、contexts.json 一樣。phrases.json 是使用者唯一不可取代
的資料，改它的格式要背一個遷移；這個檔壞掉或不見只讓排序退回原本的樣子。
"""

from __future__ import annotations

import time
from pathlib import Path

from .storage import load_json_object, save_json_object

# 每寫入這麼多次才存檔一次。save_json_object 會 fsync 加原子替換，每次送出都做
# 一遍正是按鍵追蹤犯過的錯：它每個按鍵都寫，長到 742 KB 還拖慢打字。
FLUSH_EVERY = 20

MAX_READINGS = 20_000
TRIM_TO = 15_000


class WordUsageStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._counts: dict[str, dict[str, int]] = {}
        self._touched = 0
        if self.path is not None and self.path.exists():
            self.load()

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def load(self) -> None:
        if self.path is None:
            return
        raw = load_json_object(self.path)
        entries = raw.get("counts", raw) if isinstance(raw, dict) else {}
        cleaned: dict[str, dict[str, int]] = {}
        for reading, words in entries.items():
            if not isinstance(reading, str) or not isinstance(words, dict):
                continue
            counted = {}
            for word, count in words.items():
                try:
                    counted[str(word)] = int(count)
                except (TypeError, ValueError):
                    continue
            if counted:
                cleaned[reading] = counted
        self._counts = cleaned

    def flush(self, force: bool = False) -> None:
        if self.path is None:
            return
        if self._touched == 0 and not force:
            return
        self._trim()
        save_json_object(
            self.path, {"version": 1, "updated": int(time.time()), "counts": self._counts}
        )
        self._touched = 0

    def record(self, readings: list[str], word: str) -> None:
        """數一次「這串讀音被打成這個詞」。"""
        if len(readings) < 2 or len(readings) != len(word):
            return
        words = self._counts.setdefault(self._key(readings), {})
        words[word] = words.get(word, 0) + 1
        self._touched += 1
        if self._touched >= FLUSH_EVERY:
            self.flush()

    def count(self, readings: list[str], word: str) -> int:
        if len(readings) < 2:
            return 0
        return self._counts.get(self._key(readings), {}).get(word, 0)

    def words_for(self, readings: list[str]) -> dict[str, int]:
        return dict(self._counts.get(self._key(readings), {}))

    def _trim(self) -> None:
        if len(self._counts) <= MAX_READINGS:
            return
        # 留下總次數最高的讀音串。很少用到的讀音串本來就影響不了排序。
        ranked = sorted(
            self._counts.items(), key=lambda item: sum(item[1].values()), reverse=True
        )
        self._counts = dict(ranked[:TRIM_TO])

    def __len__(self) -> int:
        return len(self._counts)
