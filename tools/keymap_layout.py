"""讀寫自訂鍵位配置。控制台透過這支呼叫，驗證規則不會有第二份。

    python tools/keymap_layout.py --dump
    python tools/keymap_layout.py --apply candidate.json
    python tools/keymap_layout.py --reset

輸出一律是 ensure_ascii 的 JSON。PowerShell 讀子行程輸出時用的是主控台字碼頁，
注音符號直接印出去會在 cp950 以外的環境變成亂碼，甚至在 CI 的 cp1252 上直接
UnicodeEncodeError 讓輸出整個變空。\\uXXXX escape 在任何字碼頁下都一樣。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core import keymap  # noqa: E402


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def dump(path: Path) -> dict[str, Any]:
    """目前的狀態：內建鍵位、作用中的鍵位，以及這份配置有什麼問題。

    問題要一起回報。使用者手改壞了 keymap.json，輸入法會安靜地退回大千——那正是
    「我改了設定卻毫無反應」的來源，控制台必須有辦法說出原因。
    """
    problem = keymap.load_layout(path)
    return {
        "ok": True,
        "path": str(path),
        "exists": path.exists(),
        "builtin": dict(keymap.KEY_TO_SYMBOL),
        "active": keymap.active_layout(),
        "name": keymap.active_layout_name(),
        # 符號的顯示順序：照內建表的排列，聲母、介音、韻母、聲調各自成群。
        # 用 set 會讓每次開啟控制台的列順序都不一樣。
        "symbols": list(dict.fromkeys(keymap.KEY_TO_SYMBOL.values())),
        "problem": problem,
    }


def invert_symbol_table(symbols: object) -> tuple[dict[str, str] | None, str]:
    """把介面上的「符號 → 按鍵」翻成檔案格式的「按鍵 → 符號」。

    翻轉會把撞在一起的按鍵默默吃掉一個：ㄅ 和 ㄆ 都設成 1，翻完只剩一筆，接著
    驗證器會說「打不出 ㄆ」——正確，但完全沒指到使用者實際做錯的那件事。所以撞
    鍵在這裡就講清楚，說出是哪個鍵被哪些符號搶。
    """
    if not isinstance(symbols, dict) or not symbols:
        return None, "配置的內容必須是「注音符號 → 按鍵」的物件。"

    owners: dict[str, list[str]] = {}
    for symbol, key in symbols.items():
        if not isinstance(key, str) or len(key) != 1:
            return None, f"「{symbol}」的按鍵必須是單一字元，這個不是：{key!r}"
        owners.setdefault(key.lower(), []).append(str(symbol))

    clashes = {key: names for key, names in owners.items() if len(names) > 1}
    if clashes:
        listed = "；".join(
            f"「{key}」被 {'、'.join(names)} 同時使用"
            for key, names in sorted(clashes.items())
        )
        return None, f"同一個按鍵不能對到多個注音符號：{listed}"

    return {key: names[0] for key, names in owners.items()}, ""


def apply(candidate: Path, target: Path) -> dict[str, Any]:
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"讀不到候選配置：{exc}"}

    # 兩種輸入形狀：控制台送「符號 → 按鍵」（畫面上就長那樣），手寫的檔案送
    # 「按鍵 → 符號」（檔案格式本身）。
    if isinstance(raw, dict) and "symbols" in raw:
        inverted, clash = invert_symbol_table(raw.get("symbols"))
        if inverted is None:
            return {"ok": False, "error": clash}
        raw = {"name": raw.get("name"), "keys": inverted}

    layout, problem = keymap.validate_layout(raw.get("keys", raw))
    if layout is None:
        # 驗不過就不寫。控制台存下一份打不出字的配置，使用者要到下次打字才發現，
        # 而那時候已經沒有東西告訴他是哪一步做錯了。
        return {"ok": False, "error": problem}

    name = raw.get("name") if isinstance(raw, dict) else None
    payload = {
        "name": str(name) if isinstance(name, str) and name else "自訂",
        "keys": layout,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    # BOM 會讓 PIMELauncher 無聲地起不來，所以明確用不帶 BOM 的 UTF-8。
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"ok": True, "path": str(target), "count": len(layout)}


def reset(target: Path) -> dict[str, Any]:
    if target.exists():
        target.unlink()
    return {"ok": True, "path": str(target), "reset": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="讀寫自訂鍵位配置")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dump", action="store_true", help="輸出目前的鍵位狀態")
    group.add_argument("--apply", metavar="FILE", help="驗證並套用一份候選配置")
    group.add_argument("--reset", action="store_true", help="刪除自訂配置，回到內建大千")
    parser.add_argument("--path", default=None, help="配置檔位置，預設 %%APPDATA%% 底下")
    args = parser.parse_args(argv)

    target = Path(args.path) if args.path else Path(keymap.layout_path())

    if args.dump:
        emit(dump(target))
    elif args.reset:
        emit(reset(target))
    else:
        result = apply(Path(args.apply), target)
        emit(result)
        if not result["ok"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
