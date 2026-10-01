# -*- coding: utf-8 -*-
r"""重打使用者確認過的句子，數要手動選幾次字。改選字排序之前與之後都跑一次。

要用 PIME 內建的 32 位元 Python 跑，而且要先 build_pime_overlay.ps1：

    & "${env:ProgramFiles(x86)}\PIME\python\python3\python.exe" tools\replay_typing.py
    ... tools\replay_typing.py --half 1          # 前半，另一半用 --half 2
    ... tools\replay_typing.py --without-language-model
    ... tools\replay_typing.py --show-errors 20  # 只印在本機，不寫檔
    ... tools\replay_typing.py --self-test       # 證明這把尺分辨得出好壞

題庫是 %APPDATA%\PinnedBopomofo\phrases.json（讀音 -> 使用者確認過的文字）。從
空白的個人資料開始，依序打每一句；打錯就像使用者一樣，選最左邊那個錯字的正確字
（一次選字），直到整句正確，然後送出，照常學習。每一句只能用它之前的句子學，
不偷看答案。

為什麼要它：改排序時單一例子會騙人。改單字預設（pins）看似是「洗來洗去」的
原因，這把尺證實選字數完全不變；把改正記得更重讓局部指標從 79% 升到 85%，
總選字數卻從 748 變 752。2026-09-30～10-01 三次排序改版都靠它決定。

量尺本身踩過的坑（都已在這裡處理）：
* 匯入 pime_adapter_smoke 會把 APPDATA 改到另一個暫存目錄，要在匯入之後才指定。
* phrases.json 也存著被改正的「片段」（勢能、該市），單獨打本來就有歧義、使用者
  也不會單獨打；只留完整句子：讀音落在另一筆較長紀錄裡的條目會被濾掉。
* 32 位元 Python 每建一個 TextService 就載入一份詞庫，整趟只用一個。
* 候選視窗同步要關掉，否則模擬會去連使用者正在跑的候選視窗程式。

題庫裡也會有使用者當年打錯又送出的句子（稍微部一樣），所以這是低估，不是絕對值；
拿來比較兩個版本，不要拿來宣稱準確率。只輸出統計，不寫任何檔案到使用者資料夾。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
REAL_DATA = Path(os.environ.get("APPDATA", "")) / "PinnedBopomofo"

import pime_adapter_smoke as harness  # noqa: E402  (sets up PIME's import path)
from pinned_bopomofo import pinned_bopomofo_ime as ime  # noqa: E402
from pinned_bopomofo.bopomofo_core.keymap import is_typable_reading, keys_for_reading  # noqa: E402

# 匯入之後才指定：harness 匯入時會把 APPDATA 改掉。
SANDBOX = Path(tempfile.mkdtemp(prefix="bopomofo-replay-"))
(SANDBOX / "PinnedBopomofo").mkdir(parents=True)
(SANDBOX / "PinnedBopomofo" / "candidate-ui.json").write_text('{"enabled": false}', encoding="utf-8")
os.environ["APPDATA"] = str(SANDBOX)


def load_corpus(path: Path) -> list[tuple[list[str], str]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    sentences = []
    for key, text in entries.items():
        readings = key.split(" ")
        if len(readings) == len(text) and all(is_typable_reading(r) for r in readings):
            sentences.append((readings, text))
    joined = [(" " + " ".join(r) + " ", t) for r, t in sentences]
    whole = []
    for (readings, text), (key, _) in zip(sentences, joined):
        inside = any(
            key != other and key in other and text in other_text
            for other, other_text in joined
            if len(other) > len(key)
        )
        if not inside:
            whole.append((readings, text))
    return whole


class Replay:
    def __init__(self, language_model: bool = True, pairs: bool = True) -> None:
        self.service = ime.PinnedBopomofoTextService(harness.DummyClient())
        if not language_model:
            self.service.language_model = None
        if not pairs:
            self.service._pair_score = lambda left, text: 0.0
        self.sequence = 1

    def type(self, readings: list[str]) -> None:
        for reading in readings:
            for key in keys_for_reading(reading):
                harness.press(self.service, key, self.sequence)
                self.sequence += 1

    def sentence(self, readings: list[str], target: str) -> tuple[int, bool, str]:
        """Type, correct like the user would, commit. (selections, reachable, first try)"""
        service = self.service
        self.type(readings)
        first = service.compositionString
        selections = 0
        reachable = True
        for _ in range(len(target) * 3):
            current = "".join(segment.text for segment in service.segments)
            if current == target or len(current) != len(target):
                break
            index = next(i for i, (a, b) in enumerate(zip(current, target)) if a != b)
            segment = service.segments[index]
            if target[index] not in service.session.candidates_for_reading(segment.reading):
                reachable = False
                break
            service._apply_candidate_choice(ime.CandidateChoice(target[index], index, index + 1))
            service._render_buffer()
            selections += 1
        service._commit_buffer()
        return selections, reachable, first


def run(sentences, language_model=True, pairs=True, show_errors=0) -> dict:
    replay = Replay(language_model, pairs)
    total = perfect = unreachable = 0
    errors = []
    for readings, target in sentences:
        selections, reachable, first = replay.sentence(readings, target)
        total += selections
        perfect += selections == 0 and reachable
        unreachable += not reachable
        if selections and len(errors) < show_errors:
            errors.append((target, first))
    chars = sum(len(t) for _, t in sentences)
    return {"sentences": len(sentences), "chars": chars, "selections": total,
            "per100": 100 * total / max(1, chars), "perfect": perfect,
            "unreachable": unreachable, "errors": errors}


def report(label: str, result: dict) -> None:
    print(f"[{label}] {result['sentences']} 句 {result['chars']} 字：手動選字 {result['selections']} 次"
          f"（每百字 {result['per100']:.1f} 次），一次打對 {result['perfect']} 句，選不到 {result['unreachable']}")
    for target, first in result["errors"]:
        print(f"   要「{target}」 先打成「{first}」")


def self_test() -> None:
    """The ruler has to tell a better engine from a worse one, or it proves nothing."""
    corpus = [
        (["ㄨㄛˇ", "ㄕˋ", "ㄌㄜ˙", "ㄧˊ", "ㄒㄧㄚˋ"], "我試了一下"),
        (["ㄨㄛˇ", "ㄕㄨㄟˋ"], "我睡"),
        (["ㄒㄧㄚˋ", "ㄧˉ", "ㄅㄨˋ"], "下一步"),
    ]
    with_model = run(corpus)
    without = run(corpus, language_model=False)
    report("self-test 有模型", with_model)
    report("self-test 沒有模型", without)
    assert with_model["selections"] < without["selections"], (
        "量尺分不出有沒有語言模型：", with_model["selections"], without["selections"])
    assert without["selections"] >= 1 and with_model["perfect"] == len(corpus), with_model
    print("PASS: replay_typing 分辨得出有沒有語言模型")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", type=Path, default=REAL_DATA / "phrases.json")
    parser.add_argument("--half", type=int, choices=(1, 2))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--without-language-model", action="store_true")
    parser.add_argument("--without-pairs", action="store_true")
    parser.add_argument("--show-errors", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.data.is_file():
        raise SystemExit(f"找不到題庫：{args.data}")
    sentences = load_corpus(args.data)
    if args.half:
        middle = len(sentences) // 2
        sentences = sentences[:middle] if args.half == 1 else sentences[middle:]
    if args.limit:
        sentences = sentences[: args.limit]
    label = ("沒有模型" if args.without_language_model else "有模型") + (
        "、沒有連字習慣" if args.without_pairs else "")
    report(label, run(sentences, not args.without_language_model, not args.without_pairs, args.show_errors))


if __name__ == "__main__":
    main()
