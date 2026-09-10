"""在兩台機器之間合併個人詞庫。

backup_user_data.ps1 做的是快照與還原：還原會整份覆蓋，另一台機器在快照之後
學到的東西就沒了。要在桌機和筆電之間共用詞庫，需要的是合併。

用法：

    python tools/sync_user_data.py --folder D:\\OneDrive\\PinnedBopomofo
    python tools/sync_user_data.py --folder ... --dry-run     只看會變什麼

共用資料夾放哪裡由使用者決定 —— OneDrive、Dropbox、git repo、隨身碟都行。
這支工具不上傳任何東西，只讀寫那個資料夾。

合併是相加的：任何一邊有的詞都會保留，不會因為另一邊沒有就被當成刪除。唯一
會改動既有值的情況是同一個讀音在兩台機器上被記成不同的字，那會依使用次數決
定並逐條列出。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.sync import MergeReport, sync_directories  # noqa: E402


def use_utf8_output() -> None:
    """把輸出改成 UTF-8。

    這支工具會印出注音讀音和中文字。Python 在 Windows 上預設跟著主控台字碼頁
    走，於是同一段訊息在 Git Bash（UTF-8）裡是一堆亂碼，在 cp950 視窗裡才對。
    衝突清單正是使用者唯一需要逐條看懂的輸出，看不懂等於沒有這個功能。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            # 被重新導向到不支援 reconfigure 的物件時照舊輸出，不要因為
            # 印訊息這種小事讓合併整個失敗。
            pass


def default_state_root() -> Path:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(appdata) / "PinnedBopomofo"


def pime_is_running() -> bool:
    """PIMELauncher 在不在跑。判準是行程，不是登錄檔快照。

    這件事必須先問，因為執行中的輸入法把整份詞庫放在記憶體裡，任何一次學習
    都會用記憶體內容覆蓋整個 phrases.json。在那種狀態下合併，結果會在使用者
    下次選字時被蓋掉，而且過程中不會有任何錯誤訊息 —— 使用者只會發現同步
    「沒有用」，卻查不出原因。
    """
    if os.name != "nt":
        return False
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq PIMELauncher.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # 問不到就當作可能在跑，寧可多問一句也不要靜默地把合併結果丟掉。
        return True
    return "PIMELauncher" in output


def describe(report: MergeReport) -> str:
    lines: list[str] = []
    if not report.changed:
        return "兩邊已經一致，沒有東西需要合併。"

    for name, count in sorted(report.added.items()):
        lines.append(f"  {name}：從共用資料夾帶回 {count} 筆")
    for name, count in sorted(report.pushed.items()):
        lines.append(f"  {name}：推送到共用資料夾 {count} 筆")
    for name, count in sorted(report.trimmed.items()):
        lines.append(f"  {name}：超過上限，捨棄使用最少的 {count} 筆")

    if report.conflicts:
        lines.append("")
        lines.append(f"  同一讀音兩邊記法不同（{len(report.conflicts)} 筆）：")
        for conflict in report.conflicts[:20]:
            lines.append(
                f"    {conflict.key}  保留「{conflict.kept}」"
                f"，捨棄「{conflict.dropped}」（{conflict.reason}）"
            )
        if len(report.conflicts) > 20:
            lines.append(f"    ……另外還有 {len(report.conflicts) - 20} 筆")
    return "\n".join(lines)


PIME_RUNNING_MESSAGE = (
    "PIME 正在執行，已停止合併。\n"
    "\n"
    "執行中的輸入法把整份詞庫放在記憶體裡，任何一次學習都會用記憶體內容覆蓋\n"
    "整個 phrases.json。現在合併的結果會在使用者下次選字時被蓋掉，而且不會有\n"
    "任何錯誤訊息。\n"
    "\n"
    "請改用控制台的「同步」分頁 —— 它會在合併後重新啟動 PIME，讓輸入法從磁碟\n"
    "重新載入。或者先關閉輸入法再用這支工具。"
)


def as_payload(report: MergeReport, **extra: Any) -> dict[str, Any]:
    """把報告轉成機器可讀的形狀，給控制台用。

    輸出一律是 ensure_ascii 的 JSON。PowerShell 讀子行程的輸出時用的是主控台
    字碼頁，中文直接印出去會在 cp950 以外的環境變成亂碼；純 ASCII 的 \\uXXXX
    escape 在任何字碼頁下解出來都一樣，ConvertFrom-Json 會還原成正確的中文。
    """
    payload: dict[str, Any] = {
        "ok": True,
        "changed": report.changed,
        # 排版好的內文一起送出去，控制台顯示它就好。讓 PowerShell 自己從
        # added/pushed/conflicts 拼一份，就會有第二套排版規則跟這裡各說各話。
        "text": describe(report),
        "added": report.added,
        "pushed": report.pushed,
        "trimmed": report.trimmed,
        "conflicts": [
            {
                "store": c.store,
                "key": c.key,
                "kept": c.kept,
                "dropped": c.dropped,
                "reason": c.reason,
            }
            for c in report.conflicts
        ],
    }
    payload.update(extra)
    return payload


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(
        description="合併兩台機器的個人詞庫", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--folder", required=True, help="共用資料夾（OneDrive、git repo 等）")
    parser.add_argument("--state", default=None, help="本機資料夾，預設 %%APPDATA%%\\PinnedBopomofo")
    parser.add_argument("--dry-run", action="store_true", help="只顯示會變什麼，不寫入")
    parser.add_argument(
        "--force",
        action="store_true",
        help="PIME 執行中也照樣合併（呼叫端必須自己重啟 PIME）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="輸出機器可讀的 JSON，給控制台用",
    )
    args = parser.parse_args(argv)

    state_root = Path(args.state) if args.state else default_state_root()
    sync_root = Path(args.folder)

    if not state_root.exists():
        message = f"找不到本機資料夾：{state_root}"
        if args.json:
            emit_json({"ok": False, "changed": False, "error": message})
        else:
            print(message, file=sys.stderr)
        return 1

    if not args.dry_run and not args.force and pime_is_running():
        if args.json:
            emit_json(
                {"ok": False, "changed": False, "error": PIME_RUNNING_MESSAGE}
            )
        else:
            print(PIME_RUNNING_MESSAGE, file=sys.stderr)
        return 2

    report = sync_directories(state_root, sync_root, dry_run=args.dry_run)

    if args.json:
        emit_json(
            as_payload(
                report,
                dry_run=args.dry_run,
                state_root=str(state_root),
                sync_root=str(sync_root),
            )
        )
        return 0

    print(f"本機　：{state_root}")
    print(f"共用　：{sync_root}")
    print(f"模式　：{'試跑，不寫入' if args.dry_run else '合併並寫回兩邊'}")
    print()
    print(describe(report))

    if args.dry_run and report.changed:
        print()
        print("以上只是試跑。拿掉 --dry-run 才會實際寫入。")
    elif report.changed:
        print()
        print("兩邊現在內容一致。合併前的狀態可以從備份取回：")
        print("  .\\tools\\backup_user_data.ps1 -List")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
