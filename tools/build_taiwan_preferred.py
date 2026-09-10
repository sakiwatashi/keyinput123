"""同音不同寫法時，讓台灣的寫法排前面。

打「ㄐㄧㄝˋ ㄇㄧㄢˋ」出來是「界面」，「ㄓㄤˋ ㄏㄨˋ」出來是「賬戶」。這不是
排序沒調好——上游語料是大陸語料轉製的，同一個詞的兩種寫法都在裡面，而大陸那
一種帶著全部的詞頻：

    ㄓㄤˋ ㄏㄨˋ      賬戶 16605  vs  帳戶  2876
    ㄐㄧㄝˋ ㄇㄧㄢˋ   界面 14436  vs  介面   588
    ㄇㄚˊ ㄅㄧˋ      麻痹  2042  vs  麻痺     0

處理方式是把兩邊的權重對調，而不是把大陸寫法壓低。語料算出來的次數是對的——
這個詞就是這麼常用——只是在台灣它寫成另一個樣子。對調之後兩種寫法都還在候選
裡，只是台灣的那個排前面。

**為什麼是人工清單，不是字級通則。** 試過用字級替換自動掃，結果會炸：

    麵 -> 面    「下麵」不該贏過「下面」——下面是方位，麵只用在麵食
    錶 -> 表    「錶面」不該贏過「表面」——錶只用在手錶
    週 -> 周    周到、周密、周全、周旋、周折 在台灣都是對的
    製 -> 制    制裁、改制 是對的
    註 -> 注    專注 是對的
    迴 -> 回    回歸 是對的，迴只用在迴圈、迴避
    臺 -> 台    台灣人就是打「台灣」「台北」，這一族反而不能動
    牠 -> 它    它指東西、牠指動物，兩個都對

同音不代表同義。這種判斷沒有機械判準，只能一個一個看，所以它是一份清單。

    python tools/build_taiwan_preferred.py

重新產生 bopomofo_core/data/taiwan_preferred.json。這是資料不是程式：覺得哪一
組判錯了就從那個檔案刪掉，整個刪掉就回到語料原本的排序。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import ReadingPhraseLexicon  # noqa: E402

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "bopomofo_core"
    / "data"
    / "taiwan_preferred.json"
)

# 整族都成立的字：這兩個字在台灣沒有「該用另一個」的情況。
#   賬 台灣一律寫「帳」：帳戶、記帳、結帳、轉帳、帳單……
#   痹 教育部用「痺」：麻痺、痲痺、小兒麻痺
# 只有確認過整族都沒有例外的字才能放進來，其餘一律走底下的逐詞清單。
CHARACTER_FAMILIES = {"賬": "帳", "痹": "痺"}

# 逐詞：同一個字在別的詞裡是對的，只有這幾個詞要換。
#   份 -> 分  只有身分、身分證。一份、月份、股份、年份、省份 在台灣都寫「份」
WORD_PAIRS = [
    ("介面", "界面"),
    ("義大利", "意大利"),
    ("身分", "身份"),
    ("身分證", "身份證"),
]


def index_of(lexicon: ReadingPhraseLexicon) -> dict[str, set[str]]:
    return {
        key: {
            row[0]
            for row in rows
            if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
        }
        for key, rows in lexicon._entries.items()
    }


def main() -> int:
    # 上限與對調都要對照使用者實際看到的排序，所以用詞庫本身來查（異體字降權、
    # 破音字拆分都已經套好）。載入時把這個檔案關掉，免得拿上一次的產出當基準。
    lexicon = ReadingPhraseLexicon(
        taiwan_path=Path("build-time-no-taiwan-preferred.json")
    )
    names = index_of(lexicon)

    swaps: dict[str, dict[str, int]] = {}
    report: list[tuple[int, str, int, str, int, str]] = []

    def consider(key: str, preferred: str, other: str) -> None:
        readings = key.split(" ")
        low = lexicon.weight(readings, preferred)
        high = lexicon.weight(readings, other)
        if high <= low:
            return  # 台灣寫法本來就在前面，不用動
        swaps.setdefault(key, {})[preferred] = high
        swaps[key][other] = low
        report.append((high - low, preferred, low, other, high, key))

    for key, phrases in names.items():
        for phrase in sorted(phrases):
            for mainland, taiwan in CHARACTER_FAMILIES.items():
                if mainland not in phrase:
                    continue
                twin = phrase.replace(mainland, taiwan)
                if twin in phrases:
                    consider(key, twin, phrase)
        for taiwan, mainland in WORD_PAIRS:
            if taiwan in phrases and mainland in phrases:
                consider(key, taiwan, mainland)

    payload = {
        "version": 1,
        "note": "同音不同寫法時台灣寫法優先。判斷理由見 tools/build_taiwan_preferred.py。",
        "entries": swaps,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"對調 {len(report)} 組，{len(swaps)} 個讀音鍵 -> {OUTPUT}")
    for _, preferred, low, other, high, key in sorted(report, reverse=True):
        print(f"  {preferred:<8}{low:>7} -> {high:<7} 壓過 {other:<8}{high:>7}   {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
