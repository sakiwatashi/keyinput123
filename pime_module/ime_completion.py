#! python3
"""自動完成：打到一半時提示後半段，按 Tab 接上。

從 pinned_bopomofo_ime.py 拆出來的 mixin，方法原封不動。只提示、不改選字排序；
任何例外都吞掉，提示壞了絕不能擋住打字或送字。
"""

from __future__ import annotations

from keycodes import VK_CONTROL, VK_TAB

from .bopomofo_core.hidden_characters import (
    shared_hidden_characters as HIDDEN_CHARACTERS,
)
from .ime_types import BOPOMOFO_TEXT, BufferedSyllable

# 自動完成的提示框顯示多久（秒）。提示還在時 Tab 就會接上，所以提示框絕不能比
# 提示本身先消失——看不見的提示被 Tab 接上，等於暗中改字。實際上它會在組字區
# 變動、送出或按 Esc 時被明確收掉，這個時間只是保底。
COMPLETION_MESSAGE_SECONDS = 600



class CompletionMixin:
    def _completion_context(self) -> tuple[list[str], list[str]] | None:
        """組字區結尾那一段可以拿來當線索的中文：(讀音, 字)。

        只有游標在最後、沒有打到一半的注音、候選視窗沒開的時候才有。游標在句中
        時接上去的字會落在哪裡說不清楚；候選視窗開著時 Tab 旁邊還有另一個選擇
        要做，兩個框疊在一起只會讓人不知道 Tab 會做哪一件。
        """
        if not self.segments or self.session.preedit or self.showCandidates:
            return None
        if self.replacement_index is not None:
            return None
        if self.focus_index is not None and self.focus_index != len(self.segments) - 1:
            return None
        runs = self._typable_runs()
        if not runs or runs[-1][1] != len(self.segments):
            return None
        start, end = runs[-1]
        tail = self.segments[start:end]
        # 原始注音（ㄅ）也算可打的讀音，但它不是中文字，拿來當線索沒有意義。
        if any(
            len(segment.text) != 1 or segment.text in BOPOMOFO_TEXT for segment in tail
        ):
            return None
        return ([segment.reading for segment in tail], [segment.text for segment in tail])

    def _completion_key(self, completion: tuple[str, list[str]]) -> tuple:
        return (
            tuple(segment.text for segment in self.segments),
            completion[0],
        )

    def _update_completion(self) -> None:
        """每次重繪之後重算提示，有變化才告訴 PIME 顯示或收起提示框。"""
        suggestion = None
        if self.autocomplete and not self.english_mode:
            context = self._completion_context()
            if context is not None:
                try:
                    suggestion = self.completion_store.suggest(*context)
                except Exception:
                    # 提示只是附加的；算壞了就當沒有，絕不能擋住打字。
                    suggestion = None
            if suggestion is not None and (
                any(HIDDEN_CHARACTERS.is_hidden(c) for c in suggestion[0])
                or self._completion_key(suggestion) == self.completion_dismissed
            ):
                suggestion = None
        via_helper = suggestion is not None and self._helper_can_draw_hint()
        # 提示沒變、畫的地方也沒變就什麼都不送。畫的地方會變：輔助程式在遊戲
        # 前景時會拒絕連線，這時必須改回由訊息窗顯示完整文字，否則畫面上只剩
        # 一個空白的定位框，而 Tab 仍然會接上一個看不見的提示。
        if suggestion == self.completion and via_helper == self.completion_via_helper:
            return
        self.completion = suggestion
        self.completion_via_helper = via_helper
        if suggestion is None:
            self.hideMessage()
        elif via_helper:
            # 訊息窗只當定位信標：它由原廠簽章 DLL 放在游標正下方，輔助程式
            # 找到它、蓋上跟候選框同一套外觀的提示。見 native_ui/helper。
            self.showMessage(" ", COMPLETION_MESSAGE_SECONDS)
        else:
            self.showMessage(f"Tab ▸ {suggestion[0]}", COMPLETION_MESSAGE_SECONDS)
        self._mirror_candidates()

    def _helper_can_draw_hint(self) -> bool:
        try:
            return bool(self.candidate_ui.beacon_ready)
        except Exception:
            return False

    def _accepts_completion(self, keyEvent) -> bool:
        return (
            self.completion is not None
            and keyEvent.keyCode == VK_TAB
            and not self._shift_held(keyEvent)
            and not keyEvent.isKeyDown(VK_CONTROL)
        )

    def _accept_completion(self) -> None:
        """把提示的字接在組字區後面。接上去的字鎖住，但還沒送出，照常可以改。

        鎖住是因為這是使用者按 Tab 明確選的；不鎖的話詞網格下一次重排就可能把
        它改成別的字，Tab 接上的跟畫面上的就對不起來。
        不標成 user_corrected：接受提示不是修正，不該讓送出時學進 phrases.json。
        """
        text, readings = self.completion
        for character, reading in zip(text, readings):
            candidates = list(
                dict.fromkeys([character] + self.session.candidates_for_reading(reading))
            )[: self.session.max_candidates]
            self.segments.append(
                BufferedSyllable(reading=reading, candidates=candidates, locked=True)
            )
        self.focus_index = len(self.segments) - 1
        self._apply_phrase_ranking()
        self._render_buffer()

    def _record_completions(self) -> None:
        """送出時把每一段連續的中文記給自動完成。統計絕不能擋住送字。"""
        try:
            for start, end in self._typable_runs():
                run = self.segments[start:end]
                if any(
                    len(segment.text) != 1 or segment.text in BOPOMOFO_TEXT
                    for segment in run
                ):
                    continue
                self.completion_store.record(
                    [segment.reading for segment in run],
                    "".join(segment.text for segment in run),
                )
        except Exception:
            pass
