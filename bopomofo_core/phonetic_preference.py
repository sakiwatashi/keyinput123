"""要不要讓輸入法替你改讀音相近的字。

**預設關閉。** 這個專案要的自動修正是錯別字——以經→已經、迫不急待→迫不及待、
問提→問題，那些是等長、無歧義的精確替換，住在 autocorrect.py 與 common_typos.json，
跟這個開關無關，永遠是開的。

這裡講的是另一回事：把 ㄓ／ㄗ、ㄔ／ㄘ、ㄕ／ㄙ、ㄣ／ㄥ 當成可能打錯，然後去猜
你要的是讀音差一格的另一個詞。它在該猜對的時候會猜對（打 ㄧㄣ ㄍㄞ 得到「應該」），
但它同樣會改掉你本來就打對的字：ㄙˉ ㄕˉ 這兩個音節沒有對應的詞，它就挑了讀音
差一格而存在的「絲絲」；打「六扇門」會變成「六三們」。

猜錯的代價是你得回頭改一個你原本打對的字，而那比多按一次選字鍵惱人得多。所以
預設關閉，想要的人可以在控制台「狀態」分頁打開。
"""

from __future__ import annotations

import json
import os

CONFIG_NAME = "phonetic-correction.json"


def default_config_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", CONFIG_NAME)


def correction_enabled(config_path: str | None = None) -> bool:
    """只有明確的 true 才開啟。檔案不存在、壞掉、缺欄位一律當成關閉。

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
        return False
    if not isinstance(value, dict):
        return False
    return bool(value.get("enabled"))
