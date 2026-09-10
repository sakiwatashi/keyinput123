# -*- coding: utf-8 -*-
r"""量按下一個鍵到輸入法回應之間的延遲。

要用 PIME 內建的 32 位元 Python 跑，而且要先 build_pime_overlay.ps1：

    & "${env:ProgramFiles(x86)}\PIME\python\python3\python.exe" tools\measure_latency.py

**讀音一定要標聲調。** 第一聲不標的話音節不會關起來，Enter 只會響鈴，組字區
一路累積下去——量到的就不是「打一個字多久」，而是「緩衝區有十個字時多久」。
第一版就是這樣，量出最壞 33 毫秒，害我去追一個不存在的效能問題；實際上是
11 毫秒。底下那個 assert 就是為了不讓同樣的事再發生一次。
"""

import io
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="bopomofo-latency-")
_state = Path(os.environ["APPDATA"]) / "PinnedBopomofo"
_state.mkdir(parents=True, exist_ok=True)
(_state / "candidate-ui.json").write_text('{"enabled": false}', encoding="utf-8")

import pime_adapter_smoke as harness  # noqa: E402
from pinned_bopomofo.pinned_bopomofo_ime import (  # noqa: E402
    PinnedBopomofoTextService,
)
from pinned_bopomofo.bopomofo_core.keymap import keys_for_reading  # noqa: E402

SENTENCES = [
    ["ㄒㄧㄚˋ", "ㄧˉ", "ㄅㄨˋ"],
    ["ㄨㄛˇ", "ㄇㄣ˙", "ㄧㄠˋ", "ㄔˉ", "ㄈㄢˋ"],
    ["ㄓㄜˋ", "ㄗㄨㄛˋ", "ㄔㄥˊ", "ㄕˋ"],
    ["ㄒㄩㄢˊ", "ㄏㄨㄢˋ", "ㄒㄧㄠˇ", "ㄕㄨㄛˉ"],
    ["ㄗˋ", "ㄖㄢˊ", "ㄩˇ", "ㄧㄢˊ", "ㄔㄨˇ", "ㄌㄧˇ"],
]


def new_service() -> PinnedBopomofoTextService:
    service = PinnedBopomofoTextService(harness.DummyClient())
    service.handleRequest(
        {"method": "onActivate", "seqNum": 0, "isKeyboardOpen": False}
    )
    return service


def run(label: str) -> None:
    service = new_service()
    sequence = 100
    keystrokes: list[float] = []
    commits: list[float] = []
    started = time.perf_counter()
    for readings in SENTENCES:
        for reading in readings:
            for key in keys_for_reading(reading):
                mark = time.perf_counter()
                harness.press(service, key, sequence)
                sequence += 1
                keystrokes.append((time.perf_counter() - mark) * 1000)
        mark = time.perf_counter()
        harness.special_key(service, 0x0D, sequence)
        sequence += 1
        commits.append((time.perf_counter() - mark) * 1000)
        assert not service.segments, (
            "送出之後組字區沒有清空。八成是某個讀音漏了聲調，音節還開著——"
            "這時量到的是累積的緩衝區，不是一次按鍵。"
        )
    keystrokes.sort()
    commits.sort()
    print(
        "  %-6s 按鍵 n=%d 中位數 %5.2f ms  p95 %5.2f ms  最壞 %6.2f ms"
        "  |  送出中位數 %5.2f ms 最壞 %5.2f ms  |  合計 %5.0f ms"
        % (
            label,
            len(keystrokes),
            keystrokes[len(keystrokes) // 2],
            keystrokes[int(len(keystrokes) * 0.95)],
            keystrokes[-1],
            commits[len(commits) // 2],
            commits[-1],
            (time.perf_counter() - started) * 1000,
        )
    )


def main() -> int:
    mark = time.perf_counter()
    new_service()
    print("  冷啟動 %.1f ms" % ((time.perf_counter() - mark) * 1000))
    mark = time.perf_counter()
    new_service()
    print("  再啟動 %.1f ms" % ((time.perf_counter() - mark) * 1000))
    for round_number in range(1, 4):
        run("第 %d 輪" % round_number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
