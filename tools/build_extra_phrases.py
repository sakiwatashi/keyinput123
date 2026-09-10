"""補上內建詞庫缺席的常用組合。

「這座城市」打成「蔗作城市」，不是排序問題——詞庫裡根本沒有「這座」，只有「蔗作」
（權重 146）。查下去發現不是孤例：指示詞加量詞是很能產的組合，64 組裡缺 21 組，
包括「每個」「哪個」「這台」「這張」「那次」這些天天都在用的。

上游資料是語料統計出來的，語料裡沒出現夠多次的組合就不會進索引。而這一類組合的
特性正是「文法上一定合法、但個別組合的出現次數分散」。

這裡不猜詞，只列舉文法上能產的格位：指示詞 × 量詞。量詞表和方位樣態詞表分開，
因為「每」能接量詞（每個、每次）但不能接方位詞（沒有「每裡」）。已經在詞庫裡的
組合會跳過，不覆寫上游的權重。

    python tools/build_extra_phrases.py

重新產生 bopomofo_core/data/extra_phrases.json。這是資料不是程式：覺得哪個組合
不該補、或想補別的詞，直接改那個檔案；整個刪掉就回到只用上游詞庫。
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import DEFAULT_INDEX  # noqa: E402

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "bopomofo_core"
    / "data"
    / "extra_phrases.json"
)

# 補進來的權重。要壓得過同讀音的雜訊（「蔗作」146），又要遠低於真正的高頻詞
# （「這個」559659），免得扭曲別的排序。使用者實際用到的那些，會由 word_usage
# 自己往上推。
EXTRA_WEIGHT = 5000

DEMONSTRATIVES = {"這": "ㄓㄜˋ", "那": "ㄋㄚˋ", "哪": "ㄋㄚˇ", "每": "ㄇㄟˇ"}

# 真量詞：四個指示詞都能接。
CLASSIFIERS = {
    "個": "ㄍㄜˋ", "隻": "ㄓ", "位": "ㄨㄟˋ", "本": "ㄅㄣˇ", "台": "ㄊㄞˊ",
    "件": "ㄐㄧㄢˋ", "張": "ㄓㄤ", "條": "ㄊㄧㄠˊ", "場": "ㄔㄤˇ", "次": "ㄘˋ",
    "種": "ㄓㄨㄥˇ", "座": "ㄗㄨㄛˋ", "頁": "ㄧㄝˋ", "篇": "ㄆㄧㄢ",
    "段": "ㄉㄨㄢˋ", "句": "ㄐㄩˋ", "步": "ㄅㄨˋ", "點": "ㄉㄧㄢˇ",
}

# 方位與樣態：只有「這／那／哪」能接。沒有「每裡」「每些」。
POSITIONAL = {"邊": "ㄅㄧㄢ", "裡": "ㄌㄧˇ", "些": "ㄒㄧㄝ", "麼": "ㄇㄜ˙"}

# 詞庫整個沒收的常用詞。跟上面的格位不同，這些沒有規律可循，是一個一個發現的
# ——tools\missing_words.py 把使用者實際打出來的詞跟詞庫對一遍，列出查不到的。
#
# 只收通用詞。同一份清單裡也有小說名、人名、專案名，那些是使用者的閱讀與工作
# 紀錄，不該進到一個公開的資料檔裡。判準是「換一個人用這個輸入法也會打到嗎」。
#
# 這幾個的讀音鍵在詞庫裡是完全空的（一個候選都沒有），所以補進去純粹是增加，
# 不會把任何既有的詞擠下去。
VOCABULARY = {
    ("玄", "幻"): ("ㄒㄩㄢˊ", "ㄏㄨㄢˋ"),
    ("六", "扇", "門"): ("ㄌㄧㄡˋ", "ㄕㄢˋ", "ㄇㄣˊ"),
    ("修", "仙"): ("ㄒㄧㄡ", "ㄒㄧㄢ"),
    ("浮", "空"): ("ㄈㄨˊ", "ㄎㄨㄥ"),
    ("仰", "躺"): ("ㄧㄤˇ", "ㄊㄤˇ"),
}

# 「每樣」成立，其餘方位詞不接「每」。單獨列出來比在表裡開例外清楚。
EXTRA_PAIRS = {("每", "樣"): ("ㄇㄟˇ", "ㄧㄤˋ")}

# 格位能產不代表每一格都成立。「麼」只接「這／那／怎」，沒有「哪麼」。
EXCLUDED = {("哪", "麼")}


def normalize(reading: str) -> str:
    return reading if reading[-1] in "ˉˊˇˋ˙" else reading + "ˉ"


def candidate_pairs() -> dict[tuple[str, ...], tuple[str, ...]]:
    pairs: dict[tuple[str, ...], tuple[str, ...]] = {}
    for head, head_reading in DEMONSTRATIVES.items():
        for tail, tail_reading in CLASSIFIERS.items():
            pairs[(head, tail)] = (head_reading, tail_reading)
        if head == "每":
            continue
        for tail, tail_reading in POSITIONAL.items():
            pairs[(head, tail)] = (head_reading, tail_reading)
    pairs.update(EXTRA_PAIRS)
    pairs.update(VOCABULARY)
    for pair in EXCLUDED:
        pairs.pop(pair, None)
    return pairs


def main() -> int:
    with gzip.open(DEFAULT_INDEX, "rt", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]

    added: dict[str, dict[str, int]] = {}
    skipped = 0
    # 不限兩個字：格位組合都是兩個字，但底下的常用詞清單有三個字的（六扇門）。
    for characters, readings in sorted(candidate_pairs().items()):
        key = " ".join(normalize(reading) for reading in readings)
        phrase = "".join(characters)
        existing = {
            row[0]
            for row in entries.get(key, [])
            if isinstance(row, list) and len(row) == 2
        }
        if phrase in existing:
            skipped += 1
            continue
        added.setdefault(key, {})[phrase] = EXTRA_WEIGHT

    payload = {
        "version": 1,
        "note": "上游詞庫缺席的組合：指示詞 × 量詞／方位詞，加上整個沒收的常用詞。",
        "weight": EXTRA_WEIGHT,
        "entries": added,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    total = sum(len(words) for words in added.values())
    print(f"補上 {total} 個組合（詞庫已有的 {skipped} 個跳過）-> {OUTPUT}")
    for key, words in sorted(added.items()):
        for phrase in words:
            print(f"  {phrase}   {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
