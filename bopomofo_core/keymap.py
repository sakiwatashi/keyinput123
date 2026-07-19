"""Standard Taiwan (Da-Qian) keyboard mapping."""

from __future__ import annotations

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

SYMBOL_TO_KEY = {symbol: key for key, symbol in KEY_TO_SYMBOL.items()}

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


def symbol_for_key(char: str) -> str | None:
    """Return a Bopomofo symbol for a physical Da-Qian key."""

    return KEY_TO_SYMBOL.get(char.lower())


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
    """Translate canonical Bopomofo symbols to Da-Qian physical keys."""

    try:
        return "".join(SYMBOL_TO_KEY[symbol] for symbol in reading)
    except KeyError as exc:
        raise ValueError(f"不支援的注音符號：{exc.args[0]}") from exc
