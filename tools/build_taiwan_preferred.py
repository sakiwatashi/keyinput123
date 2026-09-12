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
from bopomofo_core.taiwan_frequency import TaiwanFrequency  # noqa: E402

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
# 讀音的歸屬。跟上面的台灣／大陸用字是兩回事：這裡的問題是語料把一個字收在
# 它沒有的讀音底下。
#
#   那 的讀音是 ㄋㄚˋ，哪 才是 ㄋㄚˇ。但書寫時很多人用「那」代替「哪」，
#   語料照單全收，於是「那X」大量掛在 ㄋㄚˇ 底下並壓過「哪X」：
#
#       ㄋㄚˇ            哪 33103  輸給  那 129343
#       ㄋㄚˇ ㄒㄧㄝˉ     哪些 38358  輸給  那些 118325
#       ㄋㄚˇ ㄍㄜ˙      哪個 46216  輸給  那個 118070
#
#   「那X」在 ㄋㄚˋ 底下完全正常（那個／那些／那裡都打得出來），所以把 ㄋㄚˇ
#   讓給「哪」不會讓任何字變得打不出來，只是各自回到自己的讀音。57 組。
#
# 只換「讀音正好落在那個音上的那一個字」，不是整個詞掃過去。目前的詞庫裡找不
# 到反例（鍵裡有 ㄋㄚˇ 而「那」出現在別的位置的詞：0 個），所以這一點沒有測試
# 蓋得到——寫在這裡是因為換成整詞替換要等資料變動之後才會出事，那時沒有人會
# 記得原本為什麼要看位置。
READING_OWNERS = {"ㄋㄚˇ": ("那", "哪")}

# 同分組只在權重夠高時才處理。低權重區的同分多到沒有意義，而那些詞排第一
# 第二都不影響打字。
TIE_WEIGHT_FLOOR = 5000

WORD_PAIRS = [
    ("介面", "界面"),
    # 老闆／老板 同分，而台灣詞頻表兩個都收（「板」有木板等別的用法），所以
    # 拆不開，只能逐詞列。台灣講老闆，老板不是這個意思。
    ("老闆", "老板"),
    ("義大利", "意大利"),
    ("身分", "身份"),
    ("身分證", "身份證"),
]


def tie_groups(lexicon: ReadingPhraseLexicon) -> list[tuple[str, list[str]]]:
    """同一個讀音下權重完全相同的幾個寫法。

    語料把同一個詞的兩種寫法各收一次、給了一模一樣的次數——那是簡轉繁留下的
    痕跡，不是「這兩個詞一樣常用」的統計結果。權重相同，誰排第一就只看插入
    順序，等於沒有依據：

        ㄩˊ ㄕˋ      于是 92369 / 於是 92369
        ㄈㄨˋ ㄒㄧˊ   復習 39252 / 複習 39252
        ㄓˋ ㄗㄨㄛˋ   制作 33001 / 製作 33001

    權重門檻只是為了不去動幾乎沒人打的詞——同分在低權重區大量存在，那些排
    第一第二都無所謂。
    """
    groups: list[tuple[str, list[str]]] = []
    for key, rows in lexicon._entries.items():
        width = len(key.split(" "))
        if not 2 <= width <= 4:
            continue
        by_weight: dict[int, list[str]] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase = row[0]
            if not isinstance(phrase, str) or len(phrase) != width:
                continue
            try:
                by_weight.setdefault(int(row[1]), []).append(phrase)
            except (TypeError, ValueError):
                continue
        for weight, members in by_weight.items():
            if weight >= TIE_WEIGHT_FLOOR and len(members) >= 2:
                groups.append((key, members))
    return groups


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
        if high < low:
            return  # 台灣寫法本來就在前面，不用動
        if high == low:
            # 同分：誰排第一只看插入順序，權重看不出來，要問實際的候選順序。
            # 加一分就夠——目的是排到前面，不是把對方壓下去。
            order = lexicon.candidates(readings, 20)
            if preferred in order and other in order:
                if order.index(preferred) < order.index(other):
                    return
            swaps.setdefault(key, {})[preferred] = low + 1
            report.append((1, preferred, low, other, high, key))
            return
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

        readings = key.split(" ")
        for index, reading in enumerate(readings):
            owner = READING_OWNERS.get(reading)
            if owner is None:
                continue
            borrowed, rightful = owner
            for phrase in sorted(phrases):
                if len(phrase) != len(readings) or phrase[index] != borrowed:
                    continue
                twin = phrase[:index] + rightful + phrase[index + 1:]
                if twin in phrases:
                    consider(key, twin, phrase)

    # 同分組：權重一樣就沒有依據，用台灣詞頻表這份獨立的來源當判準。只有
    # 「剛好一個被收錄」才動——兩個都收（老闆／老板）或都沒收（詞匯／詞彙）
    # 表示這份資料分不出來，那就別猜，維持原樣。
    frequency = TaiwanFrequency()
    tie_broken = 0
    for key, members in tie_groups(lexicon):
        recognised = [
            phrase for phrase in members if frequency.contains_phrase(phrase)
        ]
        if len(recognised) != 1:
            continue
        preferred = recognised[0]
        if members.index(preferred) == 0:
            continue          # 本來就排第一
        readings = key.split(" ")
        weight = lexicon.weight(readings, preferred)
        swaps.setdefault(key, {})[preferred] = weight + 1
        tie_broken += 1
        report.append((1, preferred, weight, members[0], weight, key))
    print(f"同分組由台灣詞頻表拆開 {tie_broken} 組")

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
