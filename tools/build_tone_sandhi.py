"""補上「一」「不」另一種唸法查不到的詞。

「幫我一個忙」打出來是「幫我一各忙」。原因不是排序：詞庫把「一個」只收在
ㄧˉ ㄍㄜˋ 底下，而這個詞唸出來是 yí ge——照著唸打 ㄧˊ ㄍㄜˋ，兩字詞一個
都查不到，只能逐字拼，「各」（29921）就有機會冒出來。

反過來也一樣，而且更嚴重：「不是」「不要」在詞庫裡只收了變調的 ㄅㄨˊ，本調
ㄅㄨˋ ㄕˋ、ㄅㄨˋ ㄧㄠˋ 查下去一個詞都沒有。本調正是學校教的打法。

變調是規則，不是例外：

    一  在四聲前唸 ㄧˊ（一個、一下、一樣）
        在一二三聲前唸 ㄧˋ（一起、一直、一些）
    不  在四聲前唸 ㄅㄨˊ（不是、不會、不對）
        其餘不變

上游語料兩種唸法都收了一些，但都不完整。這支腳本把每個含「一」「不」的詞補
到兩邊：本調（字典唸法，學校教的打法）和照規則算出來的口語唸法。

    python tools/build_tone_sandhi.py

重新產生 bopomofo_core/data/tone_sandhi.json。這是資料不是程式：不想要某一筆
就從那個檔案刪掉，整個刪掉就回到只認語料原本收的唸法。
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import (  # noqa: E402
    DEFAULT_INDEX,
    ReadingPhraseLexicon,
)

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "bopomofo_core"
    / "data"
    / "tone_sandhi.json"
)

TONES = "ˉˊˇˋ˙"

# 本調，以及這個字所有會出現的聲調變體。只認這張表裡的讀音，別的讀音一律不碰
# ——「不」還有 ㄈㄡˇ 的唸法（不字），那不是變調，改了就是造出假詞。
BASE_READING = {"一": "ㄧˉ", "不": "ㄅㄨˋ"}
TONE_VARIANTS = {"一": {"ㄧˉ", "ㄧˊ", "ㄧˋ"}, "不": {"ㄅㄨˋ", "ㄅㄨˊ"}}

# 序數和月份的「一」不變調：第一名唸 dì-yī-míng 不是 dì-yì-míng，一月唸
# yī-yuè 不是 yí-yuè。少了這條，「第一名」會被寫成 ㄉㄧˋ ㄧˋ ㄇㄧㄥˊ，而
# 「一月」會在 ㄧˊ ㄩㄝˋ 上把真的變調詞「一躍」擠到後面。「第」不一定緊鄰著
# 「一」——第十一屆中間隔了數字——所以看的是整個前綴。
ORDINAL_PREFIX = "第"
DATE_UNITS = "月號日"


def tone_of(reading: str) -> str:
    return reading[-1] if reading and reading[-1] in TONES else "ˉ"


def base_key(phrase: str, readings: list[str]) -> list[str] | None:
    """把每個「一」「不」還原成本調。全都已經是本調就回 None。"""
    out = list(readings)
    changed = False
    for index, character in enumerate(phrase):
        variants = TONE_VARIANTS.get(character)
        if variants is None or readings[index] not in variants:
            continue
        if out[index] != BASE_READING[character]:
            out[index] = BASE_READING[character]
            changed = True
    return out if changed else None


def spoken_key(phrase: str, base: list[str]) -> list[str] | None:
    """照變調規則唸出來的讀音。規則是決定性的，一個詞只會有一種唸法。

    輕聲不處理：「一下」「不了」的實際唸法因人因句而異，猜錯會塞一個沒人要的
    詞進去，而這裡的整個重點是補真的會被打出來的唸法。
    """
    out = list(base)
    changed = False
    for index, character in enumerate(phrase):
        if character not in BASE_READING or base[index] != BASE_READING[character]:
            continue
        if index + 1 >= len(phrase):
            break  # 詞尾的「一」「不」後面沒有字可以觸發變調
        tone = tone_of(base[index + 1])
        if tone == "˙":
            continue
        if character == "一":
            if ORDINAL_PREFIX in phrase[:index] or phrase[index + 1] in DATE_UNITS:
                continue  # 第一名、第十一屆、一月：序數與月份不變調
            out[index] = "ㄧˊ" if tone == "ˋ" else "ㄧˋ"
            changed = True
        elif character == "不" and tone == "ˋ":
            out[index] = "ㄅㄨˊ"
            changed = True
    return out if changed else None


def capped(weight: int, key: str, lexicon: ReadingPhraseLexicon) -> int:
    """補進來的詞不准贏過本來就唸這個音的詞。

    「不對」唸 bú duì，本調寫法是 ㄅㄨˋ ㄉㄨㄟˋ；但那也正是「部隊」的讀音，
    而部隊沒有變調，那就是它唯一的唸法。照原權重補進去，打 ㄅㄨˋ ㄉㄨㄟˋ 會
    先拿到「不對」，把「部隊」擠掉——修好一種打法卻弄壞另一種。同樣的情形有
    27 筆，包括步調輸給不掉、布料輸給不料。

    目的是讓這個詞打得出來，不是讓它排第一。讀音上沒有別人的鍵（一個、不是）
    照原權重進去，本來就有主人的鍵則排在主人後面。
    """
    top = lexicon.candidates(key.split(" "), 1)
    if not top:
        return weight
    return max(1, min(weight, lexicon.weight(key.split(" "), top[0]) - 1))


def main() -> int:
    with gzip.open(DEFAULT_INDEX, "rt", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]

    # 上限要對照使用者實際看到的排序，所以用詞庫本身來查（異體字降權、破音字
    # 拆分都已經套好）。載入時把這個檔案關掉，免得拿上一次的產出當基準。
    lexicon = ReadingPhraseLexicon(sandhi_path=Path("build-time-no-sandhi.json"))

    known: dict[str, set[str]] = {
        key: {
            row[0]
            for row in rows
            if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
        }
        for key, rows in entries.items()
    }

    added: dict[str, dict[str, int]] = {}
    for key, rows in entries.items():
        readings = key.split(" ")
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase, weight = row[0], row[1]
            if not isinstance(phrase, str) or len(phrase) != len(readings):
                continue
            if not any(character in BASE_READING for character in phrase):
                continue

            base = base_key(phrase, readings) or list(readings)
            for candidate in (base, spoken_key(phrase, base)):
                if candidate is None:
                    continue
                target = " ".join(candidate)
                if target == key or phrase in known.get(target, ()):
                    continue
                added.setdefault(target, {})[phrase] = capped(
                    int(weight), target, lexicon
                )

    payload = {
        "version": 1,
        "note": "「一」「不」的本調與變調唸法。規則見 tools/build_tone_sandhi.py。",
        "entries": added,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    total = sum(len(words) for words in added.values())
    print(f"補上 {total} 個唸法，{len(added)} 個讀音鍵 -> {OUTPUT}")
    ranked = sorted(
        (
            (weight, phrase, key)
            for key, words in added.items()
            for phrase, weight in words.items()
        ),
        reverse=True,
    )
    for weight, phrase, key in ranked[:12]:
        print(f"  {phrase:<8} {key:<26} {weight}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
