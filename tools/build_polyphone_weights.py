"""把破音字的總詞頻按讀音拆開。

內建索引裡，一個字在它的每一個讀音下都領到同一個數字——那是這個字的**總**詞頻。
build_reading_phrase_lexicon.py 的接合處是這樣寫的：

    character = parts[0]                      # McBopomofo：一個字一個讀音一列
    key = normalize_reading(parts[1])
    entries[key][character] = occurrences.get(character, 0)
                              # ↑ 詞頻表是純文字的，用字去查，三個讀音查到同一個數

兩邊的原始資料都沒錯，錯在接法。McBopomofo 給的是「字＋讀音」，Rime Essay 給的是
「這個字總共出現幾次」，而後者不知道其中有多少次唸哪個音。

後果：「還」的 286212 次（絕大多數是 ㄏㄞˊ）同時掛在 ㄏㄞˊ、ㄏㄨㄢˊ、ㄒㄩㄢˊ 上，
於是打「玄」得到「還」。實測有 221 個讀音的第一名因此是錯的，而且全是最常用的：
ㄉㄧˋ 給「的」不給「地」、ㄧㄡˋ 給「有」不給「又」、ㄋㄟˋ 給「那」不給「內」。

不需要重新下載上游資料。索引本身就有答案：多字詞的讀音串是明確的，所以「哪些詞
用這個字的哪個讀音」直接數得出來。按那個證據把總詞頻分掉就好。

    「還」  ㄏㄞˊ 93.4%  ㄏㄨㄢˊ 6.6%  ㄒㄩㄢˊ 0%
    「好」  ㄏㄠˇ 92.8%  ㄏㄠˋ 7.2%          ← 愛好、好奇 撐起來的
    「和」  ㄏㄜˊ 93.4%  ㄏㄨㄛˋ 1.3%        ← 和麵 撐起來的

合法但罕用的讀音（愛好的 ㄏㄠˋ）按比例保留，一個詞都沒用到的讀音才歸到底。

    python tools/build_polyphone_weights.py

重新產生 bopomofo_core/data/polyphone_weights.json。名單是資料不是程式，覺得某
個字判錯了就直接改那個檔案；整個刪掉就回到修正前的行為。
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import DEFAULT_INDEX  # noqa: E402

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "bopomofo_core"
    / "data"
    / "polyphone_weights.json"
)

# 一個詞都沒用到的讀音留這個權重。不歸零，因為零跟「詞庫根本沒有這個字」無法
# 區分，而那兩件事的後果不同——這個字還是要選得到，只是排在最後。
UNUSED_READING_WEIGHT = 1


def load_entries() -> dict[str, list]:
    with gzip.open(DEFAULT_INDEX, "rt", encoding="utf-8") as stream:
        return json.load(stream)["entries"]


def reading_evidence(entries: dict[str, list]) -> dict[tuple[str, str], int]:
    """每個「字＋讀音」被多字詞用掉多少詞頻。

    只看多字詞。單字條目正是壞掉的那一份，拿它當證據會把錯誤餵回自己。
    """
    evidence: dict[tuple[str, str], int] = defaultdict(int)
    for key, rows in entries.items():
        readings = key.split(" ")
        if len(readings) < 2:
            continue
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                continue
            phrase, weight = row[0], row[1]
            if not isinstance(phrase, str) or len(phrase) != len(readings):
                continue
            try:
                weight = int(weight)
            except (TypeError, ValueError):
                continue
            for character, reading in zip(phrase, readings):
                evidence[(character, reading)] += weight
    return evidence


def find_unsplit(entries: dict[str, list]) -> dict[str, dict[str, int]]:
    """權重在每個讀音下都一樣的字——也就是總詞頻沒被拆開的那些。"""
    by_character: dict[str, dict[str, int]] = defaultdict(dict)
    for key, rows in entries.items():
        if " " in key:
            continue
        for row in rows:
            if (
                isinstance(row, list)
                and len(row) == 2
                and isinstance(row[0], str)
                and len(row[0]) == 1
            ):
                try:
                    by_character[row[0]][key] = int(row[1])
                except (TypeError, ValueError):
                    continue
    return {
        character: readings
        for character, readings in by_character.items()
        if len(readings) > 1
        and len(set(readings.values())) == 1
        and max(readings.values()) > 0
    }


def build() -> dict[str, object]:
    entries = load_entries()
    evidence = reading_evidence(entries)
    unsplit = find_unsplit(entries)

    corrections: dict[str, dict[str, int]] = {}
    for character, readings in sorted(unsplit.items()):
        total = next(iter(readings.values()))
        shares = {
            reading: evidence.get((character, reading), 0) for reading in readings
        }
        strongest = max(shares.values())
        if strongest <= 0:
            # 這個字完全沒有出現在任何多字詞裡，沒有證據可以分。原樣留著。
            continue
        # 相對「證據最多的那個讀音」縮放，不是相對總和。
        #
        # 按總和分配會把主要讀音也扣掉：「吃」的 805 拆成 ㄐㄧˊ 208 / ㄔˉ 596，
        # 而同讀音的「嗤」不是破音字、權重原封不動是 700，於是「我要吃」變成
        # 「我要嗤」。破音字被系統性懲罰了。
        #
        # 索引裡那個數字本來就是被主要讀音撐起來的，所以主要讀音保留原值才對；
        # 要壓低的只有那些搭便車的次要讀音。
        corrections[character] = {
            reading: max(UNUSED_READING_WEIGHT, int(total * share / strongest))
            for reading, share in shares.items()
        }
    return {
        "version": 1,
        "note": (
            "破音字的每讀音權重。內建索引把總詞頻掛在每個讀音上，這裡按"
            "多字詞的證據重新分配。"
        ),
        "unused_reading_weight": UNUSED_READING_WEIGHT,
        "characters": corrections,
    }


def main() -> int:
    payload = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    characters = payload["characters"]
    print(f"{len(characters)} 個破音字 -> {OUTPUT}")

    entries = load_entries()
    changed = 0
    for reading, rows in entries.items():
        if " " in reading:
            continue
        for row in rows:
            if isinstance(row, list) and len(row) == 2 and row[0] in characters:
                before = int(row[1])
                after = characters[row[0]].get(reading, before)
                if after != before:
                    changed += 1
    print(f"受影響的單字讀音條目：{changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
