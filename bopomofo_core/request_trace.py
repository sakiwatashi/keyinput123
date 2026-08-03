"""Opt-in record of which PIME callbacks actually arrive.

Two attempts to fix the Chinese/English toggle inside console windows and
remote desktop clients were built on assumptions about which callbacks TSF
delivers there. Both were wrong. This exists so the next attempt starts from a
measurement taken in the failing environment instead.

Privacy: this records callback names, whether a key was a modifier, and
whether it was pressed or released. It never records what was typed -- no
character codes, no composition text, no application identity -- and it
never leaves the machine. It is off unless the user turns it on.
"""

from __future__ import annotations

import json
import os
import time

TRACE_NAME = "keyevent-trace.json"
LOG_NAME = "keyevent-trace.log"
MAX_LINES = 4000

VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_CAPITAL = 0x14

# Only these are named. Anything else is reported as "other" so a stray key
# code -- which is input content -- never reaches the file.
NAMED_KEYS = {
    VK_SHIFT: "Shift",
    VK_LSHIFT: "LShift",
    VK_RSHIFT: "RShift",
    VK_CONTROL: "Ctrl",
    VK_MENU: "Alt",
    VK_CAPITAL: "CapsLock",
}

# Methods worth recording. Composition traffic is deliberately excluded: it is
# noise for this question and the closest thing here to user text.
TRACKED_METHODS = {
    "filterKeyDown",
    "onKeyDown",
    "filterKeyUp",
    "onKeyUp",
    "onPreservedKey",
    "onKeyboardStatusChanged",
    "onCompartmentChanged",
    "onActivate",
    "onDeactivate",
    "onSetFocus",
    "onKillFocus",
}


def _state_root() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo")


class RequestTrace:
    def __init__(self) -> None:
        self._enabled: bool | None = None
        self._lines = 0

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            self._enabled = self._read_switch()
        return self._enabled

    def _read_switch(self) -> bool:
        path = os.path.join(_state_root(), TRACE_NAME)
        try:
            # utf-8-sig: PowerShell writes a BOM, and json.load chokes on it.
            with open(path, "r", encoding="utf-8-sig") as handle:
                return bool(json.load(handle).get("enabled", False))
        except Exception:
            # Absent or damaged means off. Tracing must never be something a
            # user ends up running without choosing to.
            return False

    def record(self, msg, reply) -> None:
        """Append one line for a tracked callback. Never raises."""
        try:
            if not self.enabled or self._lines >= MAX_LINES:
                return
            method = msg.get("method")
            if method not in TRACKED_METHODS:
                return

            parts = [time.strftime("%H:%M:%S"), method]
            key_code = msg.get("keyCode")
            if key_code is not None:
                parts.append(NAMED_KEYS.get(key_code, "other"))
            if method == "onPreservedKey":
                parts.append(str(msg.get("guid", ""))[:8])
            if isinstance(reply, dict) and "return" in reply:
                parts.append("handled" if reply["return"] else "passed")

            with open(
                os.path.join(_state_root(), LOG_NAME), "a", encoding="utf-8"
            ) as handle:
                handle.write("\t".join(parts) + "\n")
            self._lines += 1
        except Exception:
            # This runs inside every key event. A diagnostic must never be
            # able to break typing.
            pass


shared_trace = RequestTrace()
