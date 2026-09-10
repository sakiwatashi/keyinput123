# -*- coding: utf-8 -*-
r"""列出你在用、但內建詞庫沒有的詞。

打「玄幻」出來是「玄換」，不是排序問題——詞庫裡根本沒有「玄幻」這個詞，只能
逐字拼，而「換」（33491）本來就壓過「幻」（1767）。這一類詞要靠個人詞頻表學，
用滿三次才會翻過來。

這支工具把「你實際打出來的詞」跟詞庫對一遍，列出詞庫查不到的那些。它們就是每次
都要多按幾下的元凶，也是值得直接補進 bopomofo_core\data\extra_phrases.json 的
候選——補進去就不用等學滿三次。

    python tools\missing_words.py
    python tools\missing_words.py --state "D:\備份\PinnedBopomofo"
    python tools\missing_words.py --limit 50

讀的是 %APPDATA%\PinnedBopomofo 底下的 word_usage.json（送出時記的詞頻）與
phrases.json（你選字教出來的詞）。只讀不寫。

清單裡會混進另一種東西：誤學的詞條。「首有」「島了」「就只」「下一」這些不是
詞庫漏收，是你某次選錯而個人詞庫記住了。它們同樣會讓打字變難，而這裡是唯一
看得到它們的地方——控制台的「個人詞庫」分頁可以直接刪掉。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.reading_phrase_lexicon import ReadingPhraseLexicon  # noqa: E402


def default_state() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "PinnedBopomofo"


def load_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def used_words(state: Path) -> dict[tuple[str, str], int]:
    """(讀音串, 詞) -> 你用過幾次。phrases.json 沒有次數，算一次。"""
    used: dict[tuple[str, str], int] = {}

    counts = load_json(state / "word_usage.json").get("counts", {})
    if isinstance(counts, dict):
        for reading, words in counts.items():
            if not isinstance(reading, str) or not isinstance(words, dict):
                continue
            for word, count in words.items():
                try:
                    used[(reading, str(word))] = used.get((reading, str(word)), 0) + int(count)
                except (TypeError, ValueError):
                    continue

    learned = load_json(state / "phrases.json")
    for reading, word in learned.items():
        if isinstance(reading, str) and isinstance(word, str):
            used.setdefault((reading, word), 0)
            used[(reading, word)] += 1

    return used


def main() -> int:
    parser = argparse.ArgumentParser(description="列出詞庫沒有、但你在用的詞")
    parser.add_argument("--state", type=Path, default=default_state())
    parser.add_argument("--limit", type=int, default=40)
    # phrases.json 學的是「這串讀音你要什麼」，一整句也會進去。那些是個人片語，
    # 不是詞庫該有的詞，列出來只會把真正的缺口淹掉——實測 670 個缺口裡有 645 個
    # 是句子。預設只看二到四個字，那是「詞庫應該收而沒收」的長度範圍。
    parser.add_argument("--max-length", type=int, default=4)
    args = parser.parse_args()

    if not args.state.exists():
        print("找不到個人資料夾：%s" % args.state)
        return 1

    lexicon = ReadingPhraseLexicon()
    used = used_words(args.state)
    if not used:
        print("個人資料裡還沒有詞的紀錄。打一陣子中文再回來看。")
        return 0

    missing: list[tuple[int, str, str, str]] = []
    for (reading, word), count in used.items():
        readings = reading.split(" ")
        if len(readings) < 2 or len(readings) != len(word):
            continue
        if len(word) > args.max_length:
            continue
        if lexicon.weight(readings, word) > 0:
            continue
        top = lexicon.candidates(readings, 1)
        missing.append((count, word, top[0] if top else "", reading))

    print("你用過的詞：%d 個；詞庫查不到的：%d 個\n" % (len(used), len(missing)))
    if not missing:
        print("你打的詞詞庫都有。")
        return 0

    print("  %-4s %-10s %-10s %s" % ("次數", "你要的", "詞庫給的", "讀音"))
    # 次數高的排前面，同次數時短的排前面——短詞影響的句子多。
    ranked = sorted(missing, key=lambda row: (-row[0], len(row[1]), row[1]))
    for count, word, top, reading in ranked[: args.limit]:
        print("  %-4d %-10s %-10s %s" % (count, word, top or "（沒有詞）", reading))
    if len(missing) > args.limit:
        print("\n  ……還有 %d 個（--limit 可以放寬）" % (len(missing) - args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
