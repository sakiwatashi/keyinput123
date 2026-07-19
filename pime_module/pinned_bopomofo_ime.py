#! python3
"""PIME adapter for an editable, character-by-character Bopomofo buffer."""

from __future__ import annotations

import os
import time
import winsound
from dataclasses import dataclass

from keycodes import *
from textService import TextService

from . import pinned_libchewing
from .bopomofo_core.keymap import symbol_for_event
from .bopomofo_core.libchewing_provider import LibChewingProvider
from .bopomofo_core.phrase_store import PhraseStore
from .bopomofo_core.pinned_store import PinnedStore
from .bopomofo_core.session import CandidateSession
from .bopomofo_core.state import Event, EventKind


SHIFT_PUNCTUATION = {
    0x31: "！",
    0x32: "＠",
    0x33: "＃",
    0x34: "＄",
    0x35: "％",
    0x36: "……",
    0x37: "＆",
    0x38: "＊",
    0x39: "（",
    0x30: "）",
    0xBA: "：",  # Shift+;
    0xBB: "＋",  # Shift+=
    0xBC: "，",  # Shift+,
    0xBD: "——",  # Shift+-
    0xBE: "。",  # Shift+.
    0xBF: "？",  # Shift+/
    0xDB: "『",  # Shift+[
    0xDD: "』",  # Shift+]
}
VK_OEM_QUOTE = 0xDE
COMPACT_CANDIDATE_COUNT = 5


@dataclass
class BufferedSyllable:
    reading: str
    candidates: list[str]
    selected: int = 0
    locked: bool = False

    @property
    def text(self) -> str:
        return self.candidates[self.selected]


class PinnedBopomofoTextService(TextService):
    def __init__(self, client):
        super().__init__(client)
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        pin_path = os.path.join(appdata, "PinnedBopomofo", "pins.json")
        phrase_path = os.path.join(appdata, "PinnedBopomofo", "phrases.json")
        provider = LibChewingProvider(pinned_libchewing)
        self.session = CandidateSession(provider, PinnedStore(pin_path))
        self.phrase_store = PhraseStore(phrase_path)
        self.quote_open = False
        self.english_mode = False
        self.last_key_event = None
        self.last_key_down_time = 0.0
        self.pending_shift_toggle = False

        # Completed syllables remain in one TSF composition.  This keeps the
        # underline under the entire uncommitted run and makes every character
        # reachable with Left/Right instead of committing one character at a
        # time.
        self.segments: list[BufferedSyllable] = []
        self.focus_index: int | None = None
        self.replacement_index: int | None = None
        self.reading_open = False
        self.candidate_expanded = False

    @property
    def provisional(self) -> bool:
        """Compatibility name used by the smoke test and old diagnostics."""
        return bool(self.segments) and not self.session.preedit

    def onActivate(self):
        super().onActivate()
        self.setSelKeys("12345")
        self.customizeUI(
            candFontName="Microsoft JhengHei UI",
            candFontSize=18,
            candPerRow=1,
            candUseCursor=True,
        )

    def filterKeyDown(self, keyEvent):
        self.last_key_event = keyEvent
        if self.last_key_down_time == 0.0:
            self.last_key_down_time = time.time()
        if keyEvent.isKeyDown(VK_MENU):
            return False
        if keyEvent.isKeyDown(VK_CONTROL):
            return self.showCandidates and keyEvent.keyCode == VK_PRIOR
        if self.english_mode:
            return False
        if self.showCandidates and self._candidate_number(keyEvent) is not None:
            return True
        if self._shift_punctuation(keyEvent) is not None:
            return True
        if self._temporary_english_letter(keyEvent) is not None:
            return True
        if keyEvent.keyCode == VK_SPACE:
            return self.isComposing()
        if keyEvent.keyCode == VK_DOWN:
            return self._has_candidate_target()
        if keyEvent.keyCode == VK_UP:
            return self.showCandidates
        if keyEvent.keyCode in (VK_LEFT, VK_RIGHT):
            return bool(self.segments) and not self.session.preedit
        if keyEvent.keyCode in (VK_RETURN, VK_BACK, VK_ESCAPE):
            return self.isComposing()
        return symbol_for_event(keyEvent.keyCode, keyEvent.charCode) is not None

    def onKeyDown(self, keyEvent):
        if self.english_mode:
            return False
        if (
            self.showCandidates
            and keyEvent.isKeyDown(VK_CONTROL)
            and keyEvent.keyCode == VK_PRIOR
        ):
            self._pin_highlighted_candidate()
            return True

        candidate_number = self._candidate_number(keyEvent)
        if self.showCandidates and candidate_number is not None:
            self._choose_highlighted_candidate(candidate_number)
            return True

        punctuation = self._shift_punctuation(keyEvent)
        if punctuation is not None:
            self._emit_punctuation(punctuation)
            if keyEvent.keyCode == VK_OEM_QUOTE:
                self.quote_open = not self.quote_open
            return True

        english_letter = self._temporary_english_letter(keyEvent)
        if english_letter is not None:
            self._emit_temporary_english(english_letter)
            return True

        if keyEvent.keyCode == VK_DOWN and not self.showCandidates:
            if not self._has_candidate_target():
                return False
            candidates, selected = self._candidate_target()
            self.candidate_expanded = False
            visible = self._visible_candidates(candidates)
            self.setCandidateList(visible)
            self.setCandidateCursor(min(selected, len(visible) - 1))
            self.setShowCandidates(True)
            self._render_buffer(keep_candidates=True)
            return True

        if self.showCandidates and keyEvent.keyCode in (VK_UP, VK_DOWN):
            candidates, _ = self._candidate_target()
            if candidates:
                visible = self._visible_candidates(candidates)
                if (
                    keyEvent.keyCode == VK_DOWN
                    and not self.candidate_expanded
                    and len(candidates) > len(visible)
                    and self.candidateCursor == len(visible) - 1
                ):
                    self.candidate_expanded = True
                    visible = self._visible_candidates(candidates)
                    self.setCandidateList(visible)
                    self.setCandidateCursor(COMPACT_CANDIDATE_COUNT)
                else:
                    delta = -1 if keyEvent.keyCode == VK_UP else 1
                    self.setCandidateCursor(
                        (self.candidateCursor + delta) % len(visible)
                    )
                self._render_buffer(keep_candidates=True)
            return True

        if self.showCandidates and keyEvent.keyCode == VK_RETURN:
            self._choose_highlighted_candidate(self.candidateCursor)
            return True

        if keyEvent.keyCode in (VK_LEFT, VK_RIGHT):
            if not self.segments or self.session.preedit:
                return False
            if self.focus_index is None:
                self.focus_index = len(self.segments) - 1
            delta = -1 if keyEvent.keyCode == VK_LEFT else 1
            self.focus_index = max(
                -1, min(len(self.segments) - 1, self.focus_index + delta)
            )
            self._render_buffer()
            return True

        if keyEvent.keyCode == VK_SPACE:
            if not self.isComposing():
                return False
            if self.session.preedit:
                if self.reading_open and self.session.candidates:
                    self._accept_active_candidate(0)
                    return True
                event = self.session.input_symbol("ˉ")
                self._handle_session_event(event)
                return True
            self._commit_buffer(" ")
            return True

        if keyEvent.keyCode == VK_ESCAPE:
            if self.showCandidates:
                self.setShowCandidates(False)
                self._render_buffer()
            else:
                self._clear_all()
                self._render_buffer()
            return True

        if keyEvent.keyCode == VK_BACK:
            if not self.isComposing():
                return False
            if self.session.preedit:
                event = self.session.backspace()
                self.reading_open = False
                self._render_event(event)
                return True
            if self.segments:
                index = (
                    self.focus_index
                    if self.focus_index is not None
                    else len(self.segments) - 1
                )
                if index < 0:
                    self._bell("已經在文字開頭")
                    return True
                self.segments.pop(index)
                # Keep the deletion gap as the insertion point for the next
                # syllable instead of appending it at the far right.
                self.replacement_index = index
                self.reading_open = False
                self.focus_index = index - 1 if self.segments else None
                self._apply_phrase_ranking()
                self._render_buffer()
                return True
            return False

        if keyEvent.keyCode == VK_RETURN:
            if not self.isComposing():
                return False
            if self.session.preedit:
                if self.session.candidates:
                    self._accept_active_candidate(0)
                else:
                    self._bell("注音尚未完整")
                    return True
            self._commit_buffer()
            return True

        symbol = symbol_for_event(keyEvent.keyCode, keyEvent.charCode)
        if symbol is not None:
            # Ordinary typing continues at the end unless Backspace left an
            # explicit insertion gap inside the composition.
            if not self.session.preedit and self.replacement_index is None:
                self.focus_index = len(self.segments) - 1 if self.segments else None
            event = self.session.input_symbol(symbol)
            self.reading_open = False
            self._handle_session_event(event)
            return True
        return False

    def filterKeyUp(self, keyEvent):
        if (
            self.last_key_event is not None
            and self._is_shift_key(self.last_key_event.keyCode)
            and self._is_shift_key(keyEvent.keyCode)
            and self.last_key_down_time
            and time.time() - self.last_key_down_time < 0.5
        ):
            # Committing a composition from filterKeyUp races the next key:
            # this callback has no TSF edit session.  Ask PIME for onKeyUp and
            # perform the state change there instead.
            self.pending_shift_toggle = True
            self.last_key_down_time = 0.0
            return True
        self.last_key_down_time = 0.0
        return False

    def onKeyUp(self, keyEvent):
        if self.pending_shift_toggle and self._is_shift_key(keyEvent.keyCode):
            self.pending_shift_toggle = False
            self._toggle_language_mode()
            return True
        return False

    @staticmethod
    def _is_shift_key(key_code: int) -> bool:
        return key_code in (VK_SHIFT, 0xA0, 0xA1)

    def _toggle_language_mode(self) -> None:
        if self.session.preedit:
            # Microsoft Bopomofo cancels an unfinished reading when a short
            # Shift press switches language mode.  Never leave half a reading
            # stranded while English keys are passed through to the app.
            self.session.clear()
            self.replacement_index = None
            self.reading_open = False
            self._render_buffer()
        if self.segments:
            self._commit_buffer()
        self.english_mode = not self.english_mode

    def onCompositionTerminated(self, forced):
        super().onCompositionTerminated(forced)
        self._clear_all()

    def _candidate_number(self, keyEvent) -> int | None:
        if 0x31 <= keyEvent.keyCode <= 0x35:
            return keyEvent.keyCode - 0x31
        if ord("1") <= keyEvent.charCode <= ord("5"):
            return keyEvent.charCode - ord("1")
        return None

    def _shift_punctuation(self, keyEvent) -> str | None:
        if not (
            keyEvent.isKeyDown(VK_SHIFT)
            or keyEvent.isKeyDown(0xA0)  # VK_LSHIFT
            or keyEvent.isKeyDown(0xA1)  # VK_RSHIFT
        ):
            return None
        if keyEvent.keyCode == VK_OEM_QUOTE:
            return "」" if self.quote_open else "「"
        return SHIFT_PUNCTUATION.get(keyEvent.keyCode)

    def _temporary_english_letter(self, keyEvent) -> str | None:
        """Return the uppercase ASCII letter produced by Shift+A-Z.

        A standalone Shift press still toggles Chinese/English mode.  Holding
        Shift while pressing a letter is a separate, protected interaction:
        it emits one temporary English letter without changing modes.
        """
        if not any(
            keyEvent.isKeyDown(code) for code in (VK_SHIFT, 0xA0, 0xA1)
        ):
            return None
        if 0x41 <= keyEvent.keyCode <= 0x5A:
            return chr(keyEvent.keyCode)
        return None

    def _emit_temporary_english(self, letter: str) -> None:
        """Place a Shift-letter after pending Chinese text, never before it."""
        if self.session.preedit:
            # A partial syllable cannot become a Chinese character.  Discard
            # only that unfinished reading, while preserving completed text.
            self.session.clear()
            self.replacement_index = None
            self.reading_open = False
        if self.segments:
            self._commit_buffer(letter)
            return
        self._clear_all()
        self.setCompositionString("")
        self.setCompositionCursor(0)
        self.setCommitString(letter)

    def _emit_punctuation(self, punctuation: str) -> None:
        if self.session.preedit:
            self._bell("注音尚未完整")
            return
        if self.segments:
            self._commit_buffer(punctuation)
            return
        self.setCommitString(punctuation)

    def _has_candidate_target(self) -> bool:
        if self.reading_open and self.session.candidates:
            return True
        index = self._candidate_segment_index()
        return index is not None and bool(self.segments[index].candidates)

    def _candidate_segment_index(self) -> int | None:
        if self.focus_index is None or not self.segments:
            return None
        # The caret is rendered after focus_index.  Microsoft Bopomofo edits
        # the character to its right; at the end, keep the final character as
        # a convenient fallback target.
        right_index = self.focus_index + 1
        if 0 <= right_index < len(self.segments):
            return right_index
        if self.focus_index == len(self.segments) - 1:
            return self.focus_index
        return None

    def _candidate_target(self) -> tuple[list[str], int]:
        if self.reading_open and self.session.candidates:
            return self.session.candidates, 0
        index = self._candidate_segment_index()
        if index is None:
            return [], 0
        segment = self.segments[index]
        return segment.candidates, segment.selected

    def _visible_candidates(self, candidates: list[str]) -> list[str]:
        if self.candidate_expanded:
            return candidates
        return candidates[:COMPACT_CANDIDATE_COUNT]

    def _choose_highlighted_candidate(self, index: int) -> None:
        candidates, _ = self._candidate_target()
        if index < 0 or index >= len(candidates):
            self._bell("沒有這個候選字")
            return
        if self.reading_open and self.session.candidates:
            selected = candidates[index]
            self.session.pins.pin(self.session.preedit, selected)
            self.session.refresh_candidates()
            self._accept_active_candidate(0, advance_focus=True)
            return
        target_index = self._candidate_segment_index()
        if target_index is not None:
            segment = self.segments[target_index]
            selected = candidates[index]
            self.session.pins.pin(segment.reading, selected)
            segment.candidates = list(
                dict.fromkeys([selected] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            segment.locked = True
            # Move the caret past the selected character.  The character now
            # to the right becomes the next edit target automatically.
            self.focus_index = target_index
        self.setShowCandidates(False)
        self._render_buffer()

    def _pin_highlighted_candidate(self) -> None:
        candidates, _ = self._candidate_target()
        index = self.candidateCursor
        if index < 0 or index >= len(candidates):
            self._bell("沒有可固定的候選字")
            return
        selected = candidates[index]
        if self.reading_open and self.session.candidates:
            self.session.pins.pin(self.session.preedit, selected)
            self.session.refresh_candidates()
        else:
            target_index = self._candidate_segment_index()
            if target_index is None:
                self._bell("沒有可固定的候選字")
                return
            segment = self.segments[target_index]
            self.session.pins.pin(segment.reading, selected)
            segment.candidates = list(
                dict.fromkeys([selected] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            segment.locked = True
        self.setCandidateCursor(0)
        self._render_buffer(keep_candidates=True)
        self.showMessage("已固定為這個讀音的第一候選", 2)

    def _handle_session_event(self, event: Event) -> None:
        if event.kind is EventKind.UPDATED and self.session.candidates:
            self._accept_active_candidate(0)
            return
        self._render_event(event)

    def _accept_active_candidate(self, index: int, advance_focus: bool = False) -> None:
        if not self.session.candidates or not 0 <= index < len(self.session.candidates):
            self._bell("沒有這個候選字")
            return
        segment = BufferedSyllable(
            reading=self.session.preedit,
            candidates=list(self.session.candidates),
            selected=index,
            locked=advance_focus,
        )
        insertion = (
            self.replacement_index
            if self.replacement_index is not None
            else len(self.segments)
        )
        self.segments.insert(insertion, segment)
        self.session.clear()
        self.replacement_index = None
        self.reading_open = False
        self.focus_index = insertion
        if advance_focus and self.focus_index + 1 < len(self.segments):
            self.focus_index += 1
        self._apply_phrase_ranking()
        self.setShowCandidates(False)
        self._render_buffer()

    def _apply_phrase_ranking(self) -> None:
        """Use the multi-word dictionary without surrendering per-char editing."""
        if len(self.segments) < 2:
            return
        readings = [segment.reading for segment in self.segments]
        phrase = self.session.best_phrase(readings)
        if phrase and len(phrase) <= len(self.segments):
            ranked_segments = self.segments[-len(phrase):]
            for segment, suggested in zip(ranked_segments, phrase):
                if segment.locked:
                    continue
                segment.candidates = list(
                    dict.fromkeys([suggested] + segment.candidates)
                )[: self.session.max_candidates]
                segment.selected = 0

        personal_length, personal_phrase = self.phrase_store.best_suffix(
            readings
        )
        if personal_length:
            personal_segments = self.segments[-personal_length:]
            for segment, suggested in zip(personal_segments, personal_phrase):
                if segment.locked:
                    continue
                segment.candidates = list(
                    dict.fromkeys([suggested] + segment.candidates)
                )[: self.session.max_candidates]
                segment.selected = 0

    def _render_event(self, event: Event) -> None:
        self._render_buffer()
        if event.kind is EventKind.BELL:
            self._bell(event.reason)

    def _render_buffer(self, keep_candidates: bool = False) -> None:
        segment_texts = [segment.text for segment in self.segments]

        active_text = self.session.preedit
        active_index = (
            self.replacement_index
            if self.replacement_index is not None
            else len(segment_texts)
        )

        if keep_candidates and self.showCandidates:
            candidates, _ = self._candidate_target()
            if candidates and 0 <= self.candidateCursor < len(candidates):
                preview = candidates[self.candidateCursor]
                if self.reading_open and self.session.candidates:
                    active_text = preview
                else:
                    target_index = self._candidate_segment_index()
                    if target_index is not None:
                        segment_texts[target_index] = preview

        if active_text:
            segment_texts.insert(active_index, active_text)

        composition = "".join(segment_texts)
        self.setCompositionString(composition)

        if active_text:
            cursor = len("".join(segment_texts[:active_index])) + len(active_text)
        elif self.focus_index is not None and self.segments:
            cursor = len("".join(segment_texts[: self.focus_index + 1]))
        else:
            cursor = len(composition)
        self.setCompositionCursor(cursor)

        if keep_candidates and self.showCandidates:
            candidates, _ = self._candidate_target()
            self.setCandidateList(self._visible_candidates(candidates))
            # PIME replies are per key event. Re-assert visibility on every
            # navigation reply; otherwise the native UI treats the missing
            # flag as closed even though Python still thinks it is open.
            self.setShowCandidates(True)
        else:
            self.candidate_expanded = False
            self.setCandidateList([])
            self.setShowCandidates(False)
            self.setCandidateCursor(0)

    def _commit_buffer(self, suffix: str = "") -> None:
        text = "".join(segment.text for segment in self.segments)
        if not text:
            self._bell("沒有可以送出的文字")
            return
        self.phrase_store.learn(
            [segment.reading for segment in self.segments], text
        )
        self.setCommitString(text + suffix)
        self._clear_all()
        self.setCompositionString("")
        self.setCompositionCursor(0)
        self.setCandidateList([])
        self.setShowCandidates(False)

    def _clear_all(self) -> None:
        self.session.clear()
        self.segments.clear()
        self.focus_index = None
        self.replacement_index = None
        self.reading_open = False
        self.candidate_expanded = False
        self.setCandidateList([])
        self.setShowCandidates(False)
        self.setCandidateCursor(0)

    def _bell(self, reason: str) -> None:
        # SystemAsterisk is the gentler Windows information sound.  Do not
        # show a tooltip: invalid phonetics should be audible but unobtrusive.
        try:
            winsound.PlaySound(
                "SystemAsterisk",
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except RuntimeError:
            pass
