"""要不要讓輸入法替你改讀音相近的字。

台灣人常把 ㄓ／ㄗ、ㄔ／ㄘ、ㄕ／ㄙ、ㄣ／ㄥ 混在一起，所以打「ㄧㄣ ㄍㄞ」的時候
輸入法會猜你要的是「應該」。實測 1200 組隨機的兩音節組合只觸發 23 次，而且幾乎
每一次都是對的：做出、紙張、冒充、撕裂、敬老、辭呈、貶損、魚叉。

代價是它偶爾會替你改掉你本來就打對的字。打 ㄙˉ ㄕˉ 這種「兩個不相干的音節、
剛好沒有對應的詞」時，它會挑一個讀音差一格而確實存在的詞（絲絲）。你打的字仍然
在候選清單裡（師、失 就在第二、三位），但預設挑的不是它。

所以這是偏好，不是對錯。預設開啟——關掉會讓 ㄣ／ㄥ 分不清楚的人每天多按很多下，
而打錯的那一方隨時選得回來。控制台的「狀態」分頁可以切換。
"""

from __future__ import annotations

import json
import os

CONFIG_NAME = "phonetic-correction.json"


def default_config_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", CONFIG_NAME)


def correction_enabled(config_path: str | None = None) -> bool:
    """只有明確的 false 才關閉。檔案不存在、壞掉、缺欄位一律當成開啟。

    在建構時讀一次，不在打字路徑上讀——按鍵事件裡碰硬碟會卡住宿主程式的輸入執行緒。
    改了設定要重啟 PIME 才生效，控制台的切換會順便重啟。
    """
    path = config_path if config_path is not None else default_config_path()
    try:
        # utf-8-sig 而不是 utf-8：Windows PowerShell 寫這個檔會帶 BOM，而
        # json.load 會把 BOM 當成雜訊拒絕。用純 utf-8 讀，一個寫對的偏好會
        # 默默地退回預設值。
        with open(path, "r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return True
    if not isinstance(value, dict):
        return True
    enabled = value.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)
