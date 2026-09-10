"""Standard Taiwan (Da-Qian) keyboard mapping, and the user's override of it.

Two different mappings live in this file and they must not be confused:

* ``KEY_TO_SYMBOL`` is what the user's keyboard produces. This is the half a
  custom layout replaces -- somebody who learned ETEN wants ``ㄅ`` somewhere
  other than ``1``.
* ``SYMBOL_TO_KEY`` is the wire format for libchewing. ``keys_for_reading``
  feeds those characters to ``handle_Default``, and the libchewing context is
  configured with its own default (Da-Qian) keyboard. It describes libchewing,
  not the user.

Deriving the second from the first is how this file used to work, and it is a
trap: the moment a custom layout is loaded, every candidate lookup starts
sending libchewing the wrong keystrokes. Nothing crashes -- the user just gets
wrong characters for every reading, with no error anywhere. So the built-in
table is kept intact for libchewing's sake and only the typing side is
swappable.
"""

from __future__ import annotations

import os
from pathlib import Path

from .storage import load_json_object

LAYOUT_NAME = "keymap.json"

KEY_TO_SYMBOL = {
    "1": "ㄅ",
    "q": "ㄆ",
    "a": "ㄇ",
    "z": "ㄈ",
    "2": "ㄉ",
    "w": "ㄊ",
    "s": "ㄋ",
    "x": "ㄌ",
    "e": "ㄍ",
    "d": "ㄎ",
    "c": "ㄏ",
    "r": "ㄐ",
    "f": "ㄑ",
    "v": "ㄒ",
    "5": "ㄓ",
    "t": "ㄔ",
    "g": "ㄕ",
    "b": "ㄖ",
    "y": "ㄗ",
    "h": "ㄘ",
    "n": "ㄙ",
    "u": "ㄧ",
    "j": "ㄨ",
    "m": "ㄩ",
    "8": "ㄚ",
    "i": "ㄛ",
    "k": "ㄜ",
    ",": "ㄝ",
    "9": "ㄞ",
    "o": "ㄟ",
    "l": "ㄠ",
    ".": "ㄡ",
    "0": "ㄢ",
    "p": "ㄣ",
    ";": "ㄤ",
    "/": "ㄥ",
    "-": "ㄦ",
    "6": "ˊ",
    "3": "ˇ",
    "4": "ˋ",
    "7": "˙",
    " ": "ˉ",
}

# libchewing's keyboard, not the user's. Never rebuild this from a custom
# layout -- see the module docstring.
SYMBOL_TO_KEY = {symbol: key for key, symbol in KEY_TO_SYMBOL.items()}

# Every sound the input method can produce. A layout that cannot reach one of
# these leaves that sound untypeable, which is why completeness is checked
# rather than assumed.
REQUIRED_SYMBOLS = frozenset(KEY_TO_SYMBOL.values())

# What typing actually consults. Starts as Da-Qian and is replaced wholesale by
# load_layout(); never mutated in place, so a half-applied layout cannot exist.
_active_key_to_symbol: dict[str, str] = dict(KEY_TO_SYMBOL)
_active_layout_name = "大千（內建）"

# Windows virtual-key codes are stable even when overlapping key presses make
# TSF's translated charCode temporarily unavailable.
VIRTUAL_KEY_TO_CHAR = {
    **{code: chr(code).lower() for code in range(0x41, 0x5B)},
    **{code: chr(code) for code in range(0x30, 0x3A)},
    0xBA: ";",  # VK_OEM_1
    0xBC: ",",  # VK_OEM_COMMA
    0xBD: "-",  # VK_OEM_MINUS
    0xBE: ".",  # VK_OEM_PERIOD
    0xBF: "/",  # VK_OEM_2
}


def layout_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", LAYOUT_NAME)


def validate_layout(raw: object) -> tuple[dict[str, str] | None, str]:
    """Check a candidate layout, returning it or the reason it was refused.

    Refusing loudly matters more here than being permissive. A layout missing
    one symbol produces an input method that works all day and then simply
    cannot type one sound, and the user has no way to connect that to a file
    they edited a week ago.
    """
    if not isinstance(raw, dict) or not raw:
        return None, "配置檔的內容必須是「按鍵 → 注音符號」的物件。"

    layout: dict[str, str] = {}
    for key, symbol in raw.items():
        if not isinstance(key, str) or len(key) != 1:
            return None, f"按鍵必須是單一字元，這個不是：{key!r}"
        if not isinstance(symbol, str) or symbol not in REQUIRED_SYMBOLS:
            return None, f"「{key}」對應到不認得的注音符號：{symbol!r}"
        layout[key.lower()] = symbol

    missing = REQUIRED_SYMBOLS - set(layout.values())
    if missing:
        # 排序讓訊息穩定，不會每次執行換一個順序。
        listed = "、".join(sorted(missing))
        return None, f"這份配置打不出這些符號：{listed}"
    return layout, ""


def load_layout(path: str | Path | None = None) -> str:
    """Install the user's layout, or keep Da-Qian and say why.

    Returns an empty string on success, otherwise the reason. Callers are
    expected to surface that: a silently ignored layout file is the same
    failure as a silently accepted broken one -- the user changed a setting and
    nothing happened.
    """
    global _active_key_to_symbol, _active_layout_name

    resolved = Path(path) if path is not None else Path(layout_path())
    if not resolved.exists():
        _active_key_to_symbol = dict(KEY_TO_SYMBOL)
        _active_layout_name = "大千（內建）"
        return ""

    raw = load_json_object(resolved)
    layout, problem = validate_layout(raw.get("keys", raw))
    if layout is None:
        # 壞掉的配置一律退回內建大千。使用者寧可用預設鍵位打字，也不要因為改壞
        # 一個檔案就完全打不出中文。
        _active_key_to_symbol = dict(KEY_TO_SYMBOL)
        _active_layout_name = "大千（內建，因為自訂配置無效）"
        return problem

    _active_key_to_symbol = layout
    name = raw.get("name") if isinstance(raw, dict) else None
    _active_layout_name = str(name) if isinstance(name, str) and name else "自訂"
    return ""


def active_layout() -> dict[str, str]:
    """The mapping typing currently consults. A copy: callers must not mutate."""

    return dict(_active_key_to_symbol)


def active_layout_name() -> str:
    return _active_layout_name


def symbol_for_key(char: str) -> str | None:
    """Return a Bopomofo symbol for a physical key in the active layout."""

    return _active_key_to_symbol.get(char.lower())


def symbol_for_event(key_code: int, char_code: int = 0) -> str | None:
    """Resolve a symbol from the physical key, with charCode as fallback."""

    physical_char = VIRTUAL_KEY_TO_CHAR.get(key_code)
    if physical_char is not None:
        symbol = symbol_for_key(physical_char)
        if symbol is not None:
            return symbol
    if char_code:
        return symbol_for_key(chr(char_code))
    return None


def keys_for_reading(reading: str) -> str:
    """Translate Bopomofo symbols to the keystrokes libchewing expects.

    Deliberately built on the built-in table rather than the active layout.
    These characters go to ``handle_Default`` on a libchewing context using its
    own Da-Qian keyboard; following the user's layout here would send it the
    wrong keys and quietly return the wrong candidates for every reading.
    """

    try:
        return "".join(SYMBOL_TO_KEY[symbol] for symbol in reading)
    except KeyError as exc:
        raise ValueError(f"不支援的注音符號：{exc.args[0]}") from exc
