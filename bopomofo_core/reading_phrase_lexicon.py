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
DEFAULT_POLYPHONES = Path(__file__).with_name("data") / "polyphone_weights.json"
DEFAULT_EXTRA = Path(__file__).with_name("data") / "extra_phrases.json"
DEFAULT_SANDHI = Path(__file__).with_name("data") / "tone_sandhi.json"
DEFAULT_TAIWAN = Path(__file__).with_name("data") / "taiwan_preferred.json"

# 簡轉繁留下的異體字繼承了常用字在語料裡的全部詞頻，高出兩到三個數量級：
# 爲 211329 對 為 684，喫 65597 對 吃 805。除以這個數字就把它放回「罕用異體」
# 該有的位置，而不是從候選裡拿掉——想打的人照樣選得到。
#
# 用除法而不是設上限：上限救不了詞組。喫飯 31690 對 吃飯 585，任何一個能壓過
# 爲(211329) 的上限都還是會高過 吃飯。比例縮放同時處理單字與詞組。
VARIANT_DEMOTION_DIVISOR = 1000

# 每個讀音的調整後候選列表算過就留著。同一個讀音在一次選字裡會被問很多次
# （組字時每按一鍵、排候選、送出時切詞），而答案在啟動之後就不會變。
# 上限存在只是為了不讓長時間執行的行程無上限成長；打字有很強的區域性，
# 幾百筆就涵蓋絕大多數查詢。
ROW_CACHE_LIMIT = 512


class ReadingPhraseLexicon:
    def __init__(
        self,
        path: str | Path = DEFAULT_INDEX,
        demotions_path: str | Path = DEFAULT_DEMOTIONS,
        polyphones_path: str | Path = DEFAULT_POLYPHONES,
        extra_path: str | Path = DEFAULT_EXTRA,
        sandhi_path: str | Path = DEFAULT_SANDHI,
        taiwan_path: str | Path = DEFAULT_TAIWAN,
    ) -> None:
        self.path = Path(path)
        self.entry_count = 0
        self._entries: dict[str, list[list[object]]] = {}
        self._demoted = self._load_demotions(Path(demotions_path))
        self._polyphones = self._load_polyphones(Path(polyphones_path))
        # 同音不同寫法時台灣寫法優先。形狀跟 _extra 一樣（讀音 -> 詞 -> 權重），
        # 但用途相反：這裡是蓋掉語料已經有的權重，不是補語料沒有的詞。
        self._taiwan = self._load_extra(Path(taiwan_path))
        self._extra = self._load_extra(Path(extra_path))
        # 變調唸法補在同一個備援表裡：兩者都是「上游詞庫查不到，但使用者真的
        # 會這樣打」。手工列的那份優先，免得規則產生的資料蓋掉刻意挑的權重。
        for key, words in self._load_extra(Path(sandhi_path)).items():
            target = self._extra.setdefault(key, {})
            for phrase, weight in words.items():
                target.setdefault(phrase, weight)
        self._row_cache: dict[str, tuple[list[tuple[str, int]], dict[str, int]]] = {}
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
    def _load_polyphones(path: Path) -> dict[str, dict[str, int]]:
        """每讀音的正確權重。缺檔或壞檔就用索引裡原本的數字。

        跟異體字名單一樣，這只調整排序，不是輸入法能不能啟動的必要條件。
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            characters = raw.get("characters", {})
            if not isinstance(characters, dict):
                return {}
            return {
                character: {
                    str(reading): int(weight)
                    for reading, weight in readings.items()
                }
                for character, readings in characters.items()
                if isinstance(character, str)
                and len(character) == 1
                and isinstance(readings, dict)
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    @staticmethod
    def _load_extra(path: Path) -> dict[str, dict[str, int]]:
        """補上游詞庫缺席的組合。缺檔就只用上游那一份。"""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw.get("entries", {})
            if not isinstance(entries, dict):
                return {}
            return {
                str(key): {
                    str(phrase): int(weight) for phrase, weight in words.items()
                }
                for key, words in entries.items()
                if isinstance(words, dict)
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    @staticmethod
    def _key(readings: list[str]) -> str:
        return " ".join(readings)

    def _adjusted(self, reading: str, phrase: str, raw: int) -> int:
        """索引裡的原始權重，套上每讀音拆分與異體字降權。

        weight() 和 candidates() 都要這個答案。分開實作過一次，結果是權重改對了
        而候選順序沒跟著改——「這裡」打得對，按 ↓ 卻還是「這裏」排第一。
        """
        weight = max(0, raw)
        if len(phrase) == 1:
            corrected = self._polyphones.get(phrase, {}).get(reading)
            if corrected is not None:
                weight = corrected
        preferred = self._taiwan.get(reading, {}).get(phrase)
        if preferred is not None:
            # 台灣寫法排前面。放在破音字之後：這張表是按 (讀音, 詞) 指定的，
            # 比按 (字, 讀音) 拆出來的破音字權重更明確。
            weight = preferred
        if self._demoted and any(
            character in self._demoted for character in phrase
        ):
            # 保底 1：降權是排到後面，不是從詞庫裡刪掉。掉到 0 會讓它跟「詞庫
            # 根本沒有這個詞」無法區分，而那兩件事的後果不同。
            return max(1, weight // VARIANT_DEMOTION_DIVISOR)
        return weight

    def _cached(self, key: str) -> tuple[list[tuple[str, int]], dict[str, int]]:
        """這個讀音的候選：排好序的清單，加上一份查權重用的表。

        兩者一起算、一起快取，因為它們必須是同一組數字。分開算過一次，結果是
        權重改對了而候選順序沒跟著改。

        排序只做一次，而且直接用列上的原始值算。先前的版本在排序鍵裡呼叫
        weight()，而 weight() 每次都重新線性掃描同一份列表——實測破音字讀音的
        candidates() 因此慢了四倍（9.2µs -> 35.7µs），而它每個按鍵會被呼叫很多次。
        """
        cached = self._row_cache.get(key)
        if cached is not None:
            return cached

        rows: list[tuple[str, int]] = []
        reorder = False
        for row in self._entries.get(key, []):
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase = row[0]
            if not isinstance(phrase, str):
                continue
            try:
                raw = int(row[1])
            except (TypeError, ValueError):
                continue
            adjusted = self._adjusted(key, phrase, raw)
            if adjusted != raw:
                # 調整過的權重跟儲存順序不再一致，這一份得重排。
                reorder = True
            rows.append((phrase, adjusted))

        known = {phrase for phrase, _ in rows}
        for phrase, weight in self._extra.get(key, {}).items():
            if phrase not in known:
                rows.append((phrase, int(weight)))
                reorder = True

        if reorder:
            rows.sort(key=lambda item: -item[1])

        # 同讀音重複的詞取第一個，跟 candidates() 挑的是同一個。
        table: dict[str, int] = {}
        for phrase, weight in rows:
            table.setdefault(phrase, weight)

        if len(self._row_cache) >= ROW_CACHE_LIMIT:
            self._row_cache.clear()
        entry = (rows, table)
        self._row_cache[key] = entry
        return entry

    def candidates(self, readings: list[str], limit: int = 20) -> list[str]:
        if not readings or limit <= 0:
            return []
        width = len(readings)
        results: list[str] = []
        for phrase, _weight in self._cached(self._key(readings))[0]:
            if len(phrase) == width and phrase not in results:
                results.append(phrase)
                if len(results) >= limit:
                    break
        return results

    def weight(self, readings: list[str], phrase: str) -> int:
        if len(phrase) != len(readings):
            return 0
        # 每按一鍵這裡會被問上千次（送出時要替每一種切法算分）。之前是每次都
        # 重新線性掃描同讀音的整份候選列表，實測佔掉打字熱路徑的六分之一。
        return self._cached(self._key(readings))[1].get(phrase, 0)

