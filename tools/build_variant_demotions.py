"""找出簡轉繁留下的異體字，產生一份降權名單。

內建詞庫來自 Rime Essay 等簡體語料轉製，而簡轉繁的對應表把常用字映射到了異體
字，於是異體字繼承了常用字在語料裡的全部詞頻。實測：

    ㄨㄟˊ   爲 211329  vs  為   684
    ㄓㄨㄛˊ  着  94513  vs  著  4115
    ㄔˉ    喫  65597  vs  吃   805
    ㄌㄧˇ   裏  45267  vs  裡 11636

後果是使用者打「我要吃」得到「我要喫」、打「這裡」得到「這裏」，而且怎麼選都
改不掉——詞網格是直接把選中的字寫進組字區的，繞過候選字過濾，所以「一律隱藏」
那份名單對它完全無效（實測確認）。

判準只用兩份已經在專案裡的資料，不靠人工判斷哪個字「比較正統」：

  1. 這個字的台灣字頻是 0（1996 年教育部常用語詞調查沒有收錄）
  2. 同一個讀音下，有另一個字的台灣字頻大於 0
  3. 而它的詞庫權重卻高過那個字

三個條件同時成立，就是轉換痕跡而不是真實用法。

不要另外加權重門檻。第一版設了 2000，於是「癡」（權重 1331、字頻 0）漏網，
把「喫」壓下去之後換成它排第一——使用者打「我要吃」拿到「我要癡」。條件三
（權重高過同音常用字）本來就是篩選器，額外的門檻只會製造這種洞。
實測：門檻 100 與 1 都得到同樣的 51 個字，這個判準自己會收斂。

    python tools/build_variant_demotions.py

重新產生 bopomofo_core/data/variant_demotions.json。名單是資料不是程式，覺得某
個字判錯了就直接改那個檔案。
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import DEFAULT_INDEX  # noqa: E402
from bopomofo_core.taiwan_frequency import TaiwanFrequency  # noqa: E402

OUTPUT = Path(__file__).resolve().parent.parent / "bopomofo_core" / "data" / (
    "variant_demotions.json"
)

# 只排除權重 0 的空條目。真正的篩選是「權重高過同音常用字」那一條。
MINIMUM_WEIGHT = 1


def find_variants() -> dict[str, list]:
    frequency = TaiwanFrequency()
    with gzip.open(DEFAULT_INDEX, "rt", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]

    found: dict[str, list] = {}
    for reading, rows in entries.items():
        if " " in reading:
            continue  # 單字讀音才比得出「同音的常用字」
        scored = [
            (row[0], int(row[1]))
            for row in rows
            if isinstance(row, list)
            and len(row) == 2
            and isinstance(row[0], str)
            and len(row[0]) == 1
        ]
        if len(scored) < 2:
            continue

        known = [
            (character, weight, frequency.score(character))
            for character, weight in scored
            if frequency.score(character) > 0
        ]
        if not known:
            continue
        common = max(known, key=lambda item: item[2])

        for character, weight in scored:
            if frequency.score(character) > 0:
                continue
            if weight <= common[1] or weight < MINIMUM_WEIGHT:
                continue
            # 同一個字可能出現在多個讀音下（着 有五個）。留下證據最強的那筆。
            previous = found.get(character)
            if previous is None or weight > previous[1]:
                found[character] = [reading, weight, common[0], common[1], common[2]]
    return found


def main() -> int:
    found = find_variants()
    payload = {
        "version": 1,
        "note": "簡轉繁留下的異體字。台灣字頻 0，卻在同讀音下權重高過有字頻的字。",
        "minimum_weight": MINIMUM_WEIGHT,
        "characters": {
            character: {
                "reading": evidence[0],
                "weight": evidence[1],
                "common": evidence[2],
                "common_weight": evidence[3],
                "common_frequency": evidence[4],
            }
            for character, evidence in sorted(
                found.items(), key=lambda item: -item[1][1]
            )
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{len(found)} 個異體字 -> {OUTPUT}")
    for character, evidence in sorted(found.items(), key=lambda item: -item[1][1]):
        reading, weight, common, common_weight, common_frequency = evidence
        print(
            f"  {character}  {reading:<8} 權重 {weight:>7}"
            f"   vs  {common} 權重 {common_weight:>6} 字頻 {common_frequency}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
