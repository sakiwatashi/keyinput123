"""Small Windows keyboard-feel lab for the Bopomofo editing core."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import winsound

from .keymap import symbol_for_key
from .state import BopomofoEditor, Event, EventKind


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("微軟注音式核心行為測試器")
        self.geometry("650x330")
        self.minsize(560, 300)
        self.editor = BopomofoEditor()
        self.preedit_var = tk.StringVar(value="（請直接按標準注音鍵盤）")
        self.status_var = tk.StringVar(value="尚未輸入")

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="目前音節（只保留一個，不連續組句）").pack(anchor="w")
        ttk.Label(
            frame,
            textvariable=self.preedit_var,
            font=("Microsoft JhengHei UI", 30),
            foreground="#1254d8",
        ).pack(anchor="w", pady=(8, 18))
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w")
        ttk.Separator(frame).pack(fill="x", pady=16)
        ttk.Label(
            frame,
            text=(
                "測試 1：依序按 v m , 4，再按 f，畫面應從 ㄒㄩㄝˋ 變成 ㄑㄩㄝˋ。\n"
                "測試 2：依序按 u v p 4，畫面應整理成 ㄒㄧㄣˋ。\n"
                "Enter 確認；Backspace 刪最近編輯的槽位；Escape 清除。"
            ),
            justify="left",
        ).pack(anchor="w")
        self.bind_all("<KeyPress>", self._on_key)
        self.after(100, self.focus_force)

    def _on_key(self, event: tk.Event) -> str | None:
        if event.keysym == "Escape":
            result = self.editor.clear()
        elif event.keysym == "BackSpace":
            result = self.editor.backspace()
        elif event.keysym in {"Return", "KP_Enter"}:
            result = self.editor.commit()
        else:
            symbol = symbol_for_key(event.char)
            if symbol is None:
                return "break"
            result = self.editor.input_symbol(symbol)

        self._render(result)
        return "break"

    def _render(self, event: Event) -> None:
        self.preedit_var.set(event.preedit or "（空白）")
        if event.kind is EventKind.UPDATED:
            self.status_var.set("音節仍可修改；同類音符會覆寫")
        elif event.kind is EventKind.COMMITTED:
            self.status_var.set(f"已確認：{event.committed}")
        elif event.kind is EventKind.CLEARED:
            self.status_var.set("已清除")
        elif event.kind is EventKind.BELL:
            self.status_var.set(f"提示音：{event.reason}")
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
