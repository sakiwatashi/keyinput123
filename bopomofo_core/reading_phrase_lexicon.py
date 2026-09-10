"""Pronunciation-aware Traditional Chinese phrase lookup.

The bundled corpus indexes phrases by their complete Bopomofo readings.  It
is deliberately separate from the text-only frequency indexes: a common word
must not be borrowed by an unrelated alternate pronunciation.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path


DEFAULT_INDEX = Path(__file__).with_name("data") / "reading_phrases.json.gz"
DEFAULT_DEMOTIONS = Path(__file__).with_name("data") / "variant_demotions.json"

# 簡轉繁留下的異體字繼承了常用字在語料裡的全部詞頻，高出兩到三個數量級：
# 爲 211329 對 為 684，喫 65597 對 吃 805。除以這個數字就把它放回「罕用異體」
# 該有的位置，而不是從候選裡拿掉——想打的人照樣選得到。
#
# 用除法而不是設上限：上限救不了詞組。喫飯 31690 對 吃飯 585，任何一個能壓過
# 爲(211329) 的上限都還是會高過 吃飯。比例縮放同時處理單字與詞組。
VARIANT_DEMOTION_DIVISOR = 1000


class ReadingPhraseLexicon:
    def __init__(
        self,
        path: str | Path = DEFAULT_INDEX,
        demotions_path: str | Path = DEFAULT_DEMOTIONS,
    ) -> None:
        self.path = Path(path)
        self.entry_count = 0
        self._entries: dict[str, list[list[object]]] = {}
        self._demoted = self._load_demotions(Path(demotions_path))
        if not self.path.exists():
            return
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as stream:
                raw = json.load(stream)
            if not isinstance(raw, dict):
                return
            meta = raw.get("meta", {})
            entries = raw.get("entries", {})
            if not isinstance(meta, dict) or not isinstance(entries, dict):
                return
            self.entry_count = int(meta.get("entry_count", 0))
            self._entries = {
                str(key): rows
                for key, rows in entries.items()
                if isinstance(rows, list)
            }
        except (OSError, ValueError, TypeError):
            self.entry_count = 0
            self._entries = {}

    @staticmethod
    def _load_demotions(path: Path) -> frozenset[str]:
        """異體字名單。缺檔或壞檔就當作空的。

        這份名單只調整排序，不是輸入法能不能啟動的必要條件——沒有它，行為就是
        加這個功能之前的樣子。為了排序而讓輸入法起不來，是完全不划算的交易。
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            characters = raw.get("characters", {})
            if not isinstance(characters, dict):
                return frozenset()
            return frozenset(
                character
                for character in characters
                if isinstance(character, str) and len(character) == 1
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return frozenset()

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def candidates(self, readings: list[str], limit: int = 20) -> list[str]:
        if not readings or limit <= 0:
            return []
        rows = self._entries.get(self._key(readings), [])
        if self._demoted and any(
            isinstance(row, list)
            and len(row) == 2
            and isinstance(row[0], str)
            and any(character in self._demoted for character in row[0])
            for row in rows
        ):
            # 這一列存的順序是原始權重的順序，降權改了權重卻改不到它。實測：
            # 這裏 降到 120、這裡 是 2791，順序卻還是 ['這裏', '這裡']，而下游
            # 取的是第一個，所以「這裡」照樣打成「這裏」。
            #
            # 只有含降權字的讀音才重排。其他讀音維持原本的順序，這個修正就不會
            # 波及到它沒有要處理的地方。
            rows = sorted(
                rows,
                key=lambda row: self.weight(readings, row[0])
                if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
                else 0,
                reverse=True,
            )
        results: list[str] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase = row[0]
            if (
                isinstance(phrase, str)
                and len(phrase) == len(readings)
                and phrase not in results
            ):
                results.append(phrase)
                if len(results) >= limit:
                    break
        return results

    def weight(self, readings: list[str], phrase: str) -> int:
        if len(phrase) != len(readings):
            return 0
        for row in self._entries.get(self._key(readings), []):
            if not isinstance(row, list) or len(row) != 2 or row[0] != phrase:
                continue
            try:
                weight = max(0, int(row[1]))
            except (TypeError, ValueError):
                return 0
            if self._demoted and any(
                character in self._demoted for character in phrase
            ):
                # 保底 1：降權是把它排到後面，不是從詞庫裡刪掉。掉到 0 會讓
                # 它跟「詞庫根本沒有這個詞」無法區分，而那兩件事的後果不同。
                return max(1, weight // VARIANT_DEMOTION_DIVISOR)
            return weight
        return 0

