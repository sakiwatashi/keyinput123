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
from .bopomofo_core.autocorrect import Autocorrector
from .bopomofo_core.candidate_ui_client import shared_client as candidate_ui_client
from .bopomofo_core.feedback_store import FeedbackStore
from .bopomofo_core.keymap import symbol_for_event
from .bopomofo_core.libchewing_provider import LibChewingProvider
from .bopomofo_core.phrase_decoder import decode_phrase_lattice
from .bopomofo_core.phrase_store import MAX_PHRASE_LENGTH, PhraseStore
from .bopomofo_core.phonetic_corrector import PhoneticCorrector
from .bopomofo_core.pinned_store import PinnedStore
from .bopomofo_core.session import CandidateSession
from .bopomofo_core.state import INITIALS, MEDIALS, RIMES, TONES, Event, EventKind


SHIFT_PUNCTUATION = {
    0x20: "ˉ",  # Shift+Space: standalone first-tone mark
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
    0xC0: "～",  # Shift+`
    0xDB: "『",  # Shift+[
    0xDC: "｜",  # Shift+\
    0xDD: "』",  # Shift+]
}
VK_OEM_QUOTE = 0xDE
CANDIDATE_PAGE_SIZE = 10
MAX_PHRASE_CHOICES = 12
CANDIDATES_PER_ROW = 2
CANDIDATE_SELECTION_LABELS = "1234567890"
NUMPAD_TEXT = {
    **{key_code: str(key_code - 0x60) for key_code in range(0x60, 0x6A)},
    0x6A: "*",  # VK_MULTIPLY
    0x6B: "+",  # VK_ADD
    0x6D: "-",  # VK_SUBTRACT
    0x6E: ".",  # VK_DECIMAL
    0x6F: "/",  # VK_DIVIDE
}
BOPOMOFO_TEXT = INITIALS | MEDIALS | RIMES | TONES


@dataclass
class BufferedSyllable:
    reading: str
    candidates: list[str]
    selected: int = 0
    locked: bool = False

    @property
    def text(self) -> str:
        return self.candidates[self.selected]


@dataclass(frozen=True)
class CandidateChoice:
    """One displayed candidate and the segment range it replaces."""

    text: str
    start: int
    end: int

    @property
    def width(self) -> int:
        return self.end - self.start


class PinnedBopomofoTextService(TextService):
    def __init__(self, client):
        super().__init__(client)
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        pin_path = os.path.join(appdata, "PinnedBopomofo", "pins.json")
        phrase_path = os.path.join(appdata, "PinnedBopomofo", "phrases.json")
        feedback_path = os.path.join(appdata, "PinnedBopomofo", "feedback.json")
        provider = LibChewingProvider(pinned_libchewing)
        self.session = CandidateSession(provider, PinnedStore(pin_path))
        self.phrase_store = PhraseStore(phrase_path)
        self.feedback_store = FeedbackStore(feedback_path)
        self.autocorrector = Autocorrector()
        self.phonetic_corrector = PhoneticCorrector(MAX_PHRASE_LENGTH)
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
        self.candidate_page = 0
        self.candidate_choices: list[CandidateChoice] = []
        self.candidate_ui = candidate_ui_client()

    def _mirror_candidates(self) -> None:
        """Sends the current candidate page to the out-of-process window.

        Visibility is driven from three separate PIME setters, so the mirror
        reads the resulting state rather than any one call's argument. That
        makes it immune to the order in which the list, the cursor, and the
        visibility flag are set during a single key event.

        The mirror is additive: what PIME's own window receives is unchanged,
        so a missing or stalled helper leaves typing exactly as it is today.
        It is also cosmetic, so no failure here may escape into the key
        handler and break composition.
        """
        try:
            if self.showCandidates and self.candidateList:
                self.candidate_ui.show(self.candidateList, self.candidateCursor or 0)
            else:
                self.candidate_ui.hide()
        except Exception:
            pass

    def handleRequest(self, msg):
        reply = super().handleRequest(msg)
        self._apply_beacon_mode(reply)
        return reply

    def _apply_beacon_mode(self, reply) -> None:
        """Shrinks PIME's own candidate window to a bare position marker.

        The out-of-process window has no way to learn where the caret is: the
        rectangle exists only inside a TSF edit session in the client process
        and no protocol field carries it. PIME's own window already knows,
        because the signed DLL moves it to the composition rectangle, and it
        does so regardless of how many candidates there are. Emptying the list
        therefore leaves a correctly positioned marker a few pixels wide, which
        the helper anchors to and covers.

        Only the value on the wire is rewritten. ``self.candidateList`` keeps
        the real page so ranking, paging and selection are untouched, and the
        mirror still sends the true list to the helper.

        This is gated on proof that the helper is alive. Without it the real
        list would exist nowhere and the user would face an empty box.
        """
        if not self.candidate_ui.beacon_ready:
            return
        if not self.showCandidates or "candidateList" not in reply:
            return
        if not reply["candidateList"]:
            return
        reply["candidateList"] = [" "]
        # A cursor past the end of the shrunken list has nothing to point at.
        reply["candidateCursor"] = 0

    def setCandidateList(self, candidates):
        super().setCandidateList(candidates)
        self._mirror_candidates()

    def setShowCandidates(self, show):
        super().setShowCandidates(show)
        self._mirror_candidates()

    def setCandidateCursor(self, pos):
        super().setCandidateCursor(pos)
        self._mirror_candidates()

    @property
    def provisional(self) -> bool:
        """Compatibility name used by the smoke test and old diagnostics."""
        return bool(self.segments) and not self.session.preedit

    def onActivate(self):
        super().onActivate()
        # Reset our field-local Shift toggle, but respect the keyboard-open
        # state supplied by TSF. Games and secure/custom controls may
        # deliberately close their input context; forcing it open here can
        # create an open/close feedback loop with the application.
        self._reset_internal_chinese_mode()
        # Each page exposes exactly ten numeric selection keys. The native UI
        # fills its two columns from top to bottom: 1-5 on the left and 6-0 on
        # the right. Keeping the native list and label string the same length
        # prevents PIME from
        # reading past the labels and painting garbage characters.
        self.setSelKeys(CANDIDATE_SELECTION_LABELS)
        self.customizeUI(
            candFontName="Microsoft JhengHei UI",
            candFontSize=16,
            candPerRow=CANDIDATES_PER_ROW,
            candUseCursor=True,
        )

    def onDeactivate(self):
        # A persistent Shift toggle is useful inside the current field, but a
        # newly focused field should always begin in Bopomofo mode.
        self.english_mode = False
        self.pending_shift_toggle = False
        self.last_key_down_time = 0.0
        # The helper draws a topmost window; leaving it up after this profile
        # goes away would strand it over an unrelated application.
        try:
            self.candidate_ui.hide()
        except Exception:
            pass

    def onKeyboardStatusChanged(self, opened):
        self.keyboardOpen = opened
        self.pending_shift_toggle = False
        self.last_key_down_time = 0.0
        if opened:
            self.english_mode = False

    def _reset_internal_chinese_mode(self) -> None:
        """Reset the field-local mode without overriding the host app."""
        self.english_mode = False
        self.pending_shift_toggle = False
        self.last_key_down_time = 0.0

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
        if self._numpad_text(keyEvent) is not None:
            return True
        if self.showCandidates and self._candidate_number(keyEvent) is not None:
            return True
        if self._shift_punctuation(keyEvent) is not None:
            return True
        if self._temporary_english_letter(keyEvent) is not None:
            return True
        if keyEvent.keyCode == VK_SPACE:
            return self.isComposing()
        if self.showCandidates and keyEvent.keyCode in (
            VK_UP,
            VK_DOWN,
            VK_LEFT,
            VK_RIGHT,
        ):
            return True
        if keyEvent.keyCode == VK_DOWN:
            return self._has_candidate_target()
        if keyEvent.keyCode in (VK_LEFT, VK_RIGHT):
            return bool(self.segments) and not self.session.preedit
        if keyEvent.keyCode in (VK_RETURN, VK_BACK, VK_ESCAPE):
            return self.isComposing()
        return symbol_for_event(keyEvent.keyCode, keyEvent.charCode) is not None

    def onKeyDown(self, keyEvent):
        if self.english_mode:
            return False
        numpad_text = self._numpad_text(keyEvent)
        if numpad_text is not None:
            self._emit_direct_text(numpad_text)
            return True
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
            # The menu must never reveal a better default that the editable
            # composition has not already adopted. Synchronize through the
            # same phrase ranking source before presenting alternatives.
            self._apply_phrase_ranking()
            self.candidate_choices = self._build_candidate_choices()
            candidates, selected = self._candidate_target()
            if not candidates:
                return False
            self.candidate_page = 0
            visible = self._visible_candidates(candidates)
            self.setCandidateList(visible)
            self.setCandidateCursor(min(selected, len(visible) - 1))
            self.setShowCandidates(True)
            self._render_buffer(keep_candidates=True)
            return True

        if self.showCandidates and keyEvent.keyCode in (
            VK_UP,
            VK_DOWN,
            VK_LEFT,
            VK_RIGHT,
        ):
            self._navigate_candidate_menu(keyEvent.keyCode)
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
                    if self._is_literal_bopomofo(self.session.candidates[0]):
                        self._emit_or_buffer_literal(self.session.candidates[0])
                        return True
                    self._accept_active_candidate(0)
                    return True
                # Space supplies the implicit first tone. Do not decide from
                # the symbol's slot alone: several symbols classed as initials
                # are also complete Mandarin syllables (ㄙ→司/思, ㄓ→之/知,
                # ㄔ→吃, ㄕ→師, ㄗ→資, ...). The dictionary is the source of
                # truth; only a reading with no Chinese candidate falls back
                # to literal Zhuyin.
                literal = self.session.preedit
                event = self.session.input_symbol("ˉ")
                if event.kind is EventKind.BELL and self.session.preedit:
                    # This exact first-tone reading has no Chinese syllable,
                    # but Microsoft Bopomofo still lets users output the raw
                    # Zhuyin symbol through the candidate window.
                    literal = self.session.preedit
                    self.session.candidates = [literal]
                    self.reading_open = True
                    self.candidate_page = 0
                    self.setCandidateList([literal])
                    self.setCandidateCursor(0)
                    self.setShowCandidates(True)
                    self._render_buffer(keep_candidates=True)
                    return True
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
            if symbol in TONES and not self.session.preedit:
                self._emit_or_buffer_literal(symbol)
                return True
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
        if forced:
            # TSF uses forced termination when focus moves to another edit
            # context. Reset our local toggle, but never fight an application
            # that intentionally disabled its IME context.
            self._reset_internal_chinese_mode()

    def _candidate_number(self, keyEvent) -> int | None:
        # The right-hand numeric keypad is text input, never a candidate key.
        if keyEvent.keyCode in NUMPAD_TEXT:
            return None
        if 0x31 <= keyEvent.keyCode <= 0x39:
            return keyEvent.keyCode - 0x31
        if keyEvent.keyCode == 0x30:
            return 9
        if ord("1") <= keyEvent.charCode <= ord("9"):
            return keyEvent.charCode - ord("1")
        if keyEvent.charCode == ord("0"):
            return 9
        return None

    @staticmethod
    def _numpad_text(keyEvent) -> str | None:
        # Use the physical virtual-key code so NumPad decimal remains a dot
        # even when PIME supplies no charCode or the Bopomofo keymap sees it.
        return NUMPAD_TEXT.get(keyEvent.keyCode)

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
        """Replace an unfinished reading with one temporary ASCII letter."""
        self._emit_direct_text(letter)

    def _emit_punctuation(self, punctuation: str) -> None:
        """Replace an unfinished reading with the requested punctuation."""
        self._emit_direct_text(punctuation)

    def _emit_or_buffer_literal(self, text: str) -> None:
        """Keep literal Bopomofo inside an existing editable composition."""
        if self.segments:
            self._buffer_literal_text(text)
        else:
            self._emit_direct_text(text)

    def _buffer_literal_text(
        self, text: str, start: int | None = None, end: int | None = None
    ) -> None:
        """Insert protected literal symbols without committing other text.

        One buffer segment is kept per Unicode symbol so readings, protection
        masks, and rendered text remain aligned even for a spelling such as
        ㄢˊ. Literal segments are locked because phrase ranking must never
        silently turn a deliberately selected phonetic spelling into Hanzi.
        """
        if not text:
            return
        if start is None:
            if self.replacement_index is not None:
                start = self.replacement_index
            elif self.focus_index is not None:
                start = self.focus_index + 1
            else:
                start = len(self.segments)
        if end is None:
            end = start
        literal_segments = [
            BufferedSyllable(
                reading=character,
                candidates=[character],
                locked=True,
            )
            for character in text
        ]
        self.segments[start:end] = literal_segments
        self.session.clear()
        self.replacement_index = None
        self.reading_open = False
        self.focus_index = start + len(literal_segments) - 1
        self._render_buffer()

    def _emit_direct_text(self, text: str) -> None:
        """Insert non-Bopomofo text at the active caret and finish composition."""
        if self.replacement_index is not None:
            insertion = self.replacement_index
        elif self.focus_index is not None:
            insertion = self.focus_index + 1
        else:
            insertion = len(self.segments)

        # A partial syllable is replaced, not committed or allowed to move the
        # direct character to another edge of the composition.
        if self.session.preedit:
            self.session.clear()
            self.reading_open = False

        if self.segments:
            left = "".join(segment.text for segment in self.segments[:insertion])
            right = "".join(segment.text for segment in self.segments[insertion:])
            self.setCommitString(left + text + right)
            self._clear_all()
            self.setCompositionString("")
            self.setCompositionCursor(0)
            return

        self._clear_all()
        self.setCompositionString("")
        self.setCompositionCursor(0)
        self.setCommitString(text)

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
        if self.candidate_choices:
            return [choice.text for choice in self.candidate_choices], 0
        index = self._candidate_segment_index()
        if index is None:
            return [], 0
        segment = self.segments[index]
        return segment.candidates, segment.selected

    def _candidate_phrase_spans(self, target: int) -> list[tuple[int, int]]:
        """Return longest-first phrase spans at the caret's edit side."""
        count = len(self.segments)
        spans: list[tuple[int, int]] = []
        max_width = min(MAX_PHRASE_LENGTH, count)
        if self.focus_index == count - 1:
            # At the end of the composition, the last character is only a
            # fallback target. Offer words ending there, including the whole
            # composition, from longest to shortest.
            for width in range(max_width, 1, -1):
                spans.append((count - width, count))
        else:
            # Elsewhere the editable character is to the right of the caret,
            # so words begin at that character, matching Microsoft Bopomofo.
            max_right_width = min(max_width, count - target)
            for width in range(max_right_width, 1, -1):
                spans.append((target, target + width))
        return spans

    def _ranked_phrase_options(self, start: int, end: int) -> list[str]:
        """Return one shared ranking for automatic text and candidate UI.

        Personal phrases win equal spans. For the whole buffer, conservative
        reading-aware and exact typo corrections are then promoted ahead of
        their uncorrected source sentences. Taiwan/frequency-backed phrases
        follow, then the conversion engine. Unverified engine guesses are
        allowed only for the whole buffer, where they represent the engine's
        sentence-level default; intermediate guesses must be known words.
        """
        if start < 0 or end > len(self.segments) or end - start < 2:
            return []
        readings = [segment.reading for segment in self.segments[start:end]]
        personal = self.phrase_store.exact(readings)
        frequent = self.session.validated_frequent_phrase_candidates(
            readings,
            [segment.candidates for segment in self.segments[start:end]],
        )
        whole_buffer = start == 0 and end == len(self.segments)
        trusted = self.session.trusted_phrase_candidates(readings)
        engine = [
            phrase
            for phrase in self.session.phrase_candidates(readings)
            if whole_buffer
            or phrase in trusted
            or self.session.is_frequent_phrase(phrase)
        ]
        corrected: list[str] = []
        contextual: list[str] = []
        current_text = "".join(
            segment.text for segment in self.segments[start:end]
        )
        if whole_buffer:
            protected = [segment.locked for segment in self.segments[start:end]]
            context_protected = list(protected)
            has_lexical_span = False
            # Exact phrases chosen by the lattice are reliable context, even
            # when the whole sentence is assembled from several dictionary
            # rows. Fuzzy correction may work around them, but must not turn
            # 層數+較高 back into an unrelated whole-engine guess.
            decoded = decode_phrase_lattice(
                readings,
                current_text,
                protected,
                self.session.lexical_phrase_candidates,
                self.session.phrase_weight,
                self.phrase_store.exact,
                MAX_PHRASE_LENGTH,
            )
            for span in decoded:
                if span.end - span.start < 2 or span.text != current_text[
                    span.start : span.end
                ]:
                    continue
                has_lexical_span = True
                for index in range(span.start, span.end):
                    context_protected[index] = True
            if has_lexical_span:
                for source in engine:
                    if len(source) != len(current_text):
                        continue
                    hybrid = "".join(
                        current if is_protected else suggested
                        for current, suggested, is_protected in zip(
                            current_text, source, context_protected
                        )
                    )
                    if (
                        hybrid != current_text
                        and all(
                            is_protected
                            or suggested in segment.candidates
                            for suggested, segment, is_protected in zip(
                                source,
                                self.segments[start:end],
                                context_protected,
                            )
                        )
                        and hybrid not in contextual
                    ):
                        contextual.append(hybrid)
            # Re-decode both the visible text and the exact-reading sources.
            # On the next render the visible text may already be corrected;
            # retaining the engine sources here makes the corrected sentence
            # reproducible as candidate zero instead of a one-frame mutation.
            for source in dict.fromkeys([current_text] + frequent + engine):
                if len(source) != end - start:
                    continue
                suggestion, phonetic_changes = self.phonetic_corrector.correct(
                    readings,
                    source,
                    protected,
                    self.session.candidates_for_reading,
                    self.session.frequent_phrase_candidates,
                    known_phrase_lookup=(
                        self.session.trusted_phrase_candidates
                    ),
                    replacement_phrase_lookup=(
                        self.session.trusted_phrase_candidates
                    ),
                )
                suggestion, typo_changes = self.autocorrector.correct(
                    suggestion, protected
                )
                if (
                    suggestion != source
                    and (phonetic_changes or typo_changes)
                    and all(
                        not is_protected or suggested == current
                        for suggested, current, is_protected in zip(
                            suggestion, current_text, context_protected
                        )
                    )
                    and suggestion not in corrected
                ):
                    corrected.append(suggestion)
        trusted_current = current_text in trusted
        trusted_front = trusted if trusted_current else []
        trusted_tail = [] if trusted_current else trusted
        return [
            phrase
            for phrase in dict.fromkeys(
                ([personal] if personal else [])
                + trusted_front
                + corrected
                + frequent
                + trusted_tail
                + [current_text]
                + contextual
                + engine
            )
            if len(phrase) == end - start
        ]

    def _build_candidate_choices(self) -> list[CandidateChoice]:
        target = self._candidate_segment_index()
        if target is None:
            return []

        phrase_choices: list[CandidateChoice] = []
        displayed: set[str] = set()
        for start, end in self._candidate_phrase_spans(target):
            current_text = "".join(
                segment.text for segment in self.segments[start:end]
            )
            for phrase in self._ranked_phrase_options(start, end):
                # Keep exactly one whole-buffer choice even when automatic
                # ranking has already adopted it.  This preserves sentence
                # selection/confirmation in the candidate editor.  Shorter
                # no-op spans are still noise: without this distinction a
                # long composition fills the menu with the sentence, minus
                # one character, minus two characters, and so on.
                whole_buffer = start == 0 and end == len(self.segments)
                if (
                    len(phrase) != end - start
                    or (phrase == current_text and not whole_buffer)
                    or phrase in displayed
                ):
                    continue
                phrase_choices.append(CandidateChoice(phrase, start, end))
                displayed.add(phrase)
                if len(phrase_choices) >= MAX_PHRASE_CHOICES:
                    break
            if len(phrase_choices) >= MAX_PHRASE_CHOICES:
                break

        segment = self.segments[target]
        single_choices: list[CandidateChoice] = []
        for candidate in segment.candidates:
            if candidate in displayed:
                continue
            single_choices.append(CandidateChoice(candidate, target, target + 1))
            displayed.add(candidate)
            if len(single_choices) >= self.session.max_candidates:
                break

        # At the end, sentence/word candidates remain first for whole-sentence
        # confirmation. After the caret is moved into the composition, the
        # user is explicitly editing the character to its right: put that
        # character's candidates first so pressing 1 cannot accidentally lock
        # the entire remaining sentence. Keep three phrase choices on page one
        # so word-level editing remains one key away.
        editing_inside = (
            self.focus_index is not None
            and self.focus_index < len(self.segments) - 1
        )
        if editing_inside:
            front_phrase_count = min(3, len(phrase_choices))
            front_single_count = CANDIDATE_PAGE_SIZE - front_phrase_count
            choices = (
                single_choices[:front_single_count]
                + phrase_choices[:front_phrase_count]
                + single_choices[front_single_count:]
                + phrase_choices[front_phrase_count:]
            )
        else:
            front_phrases = phrase_choices[:3]
            front_single_count = CANDIDATE_PAGE_SIZE - len(front_phrases)
            choices = (
                front_phrases
                + single_choices[:front_single_count]
                + phrase_choices[len(front_phrases) :]
                + single_choices[front_single_count:]
            )
        # A literal Zhuyin spelling must never disappear onto page two while
        # editing an uncommitted sentence. Keep it within the first four
        # positions without displacing the highest-ranked Chinese choice.
        literal_index = next(
            (
                index
                for index, choice in enumerate(choices)
                if choice.width == 1 and self._is_literal_bopomofo(choice.text)
            ),
            None,
        )
        if literal_index is not None and literal_index > 3:
            literal_choice = choices.pop(literal_index)
            choices.insert(3, literal_choice)
        return choices[: self.session.max_candidates]

    def _visible_candidates(self, candidates: list[str]) -> list[str]:
        start = self.candidate_page * CANDIDATE_PAGE_SIZE
        return candidates[start : start + CANDIDATE_PAGE_SIZE]

    def _absolute_candidate_index(self, page_index: int) -> int:
        return self.candidate_page * CANDIDATE_PAGE_SIZE + page_index

    @staticmethod
    def _is_literal_bopomofo(text: str) -> bool:
        return bool(text) and all(character in BOPOMOFO_TEXT for character in text)

    def _navigate_candidate_menu(self, key_code: int) -> None:
        """Navigate a ten-item, two-column page without letter labels."""
        candidates, _ = self._candidate_target()
        if not candidates:
            return
        visible = self._visible_candidates(candidates)
        cursor = min(self.candidateCursor, len(visible) - 1)

        last_page = max(0, (len(candidates) - 1) // CANDIDATE_PAGE_SIZE)
        target = cursor
        if key_code == VK_RIGHT and self.candidate_page < last_page:
            self.candidate_page += 1
            visible = self._visible_candidates(candidates)
            target = 0
            self.setCandidateList(visible)
        elif key_code == VK_LEFT and self.candidate_page > 0:
            self.candidate_page -= 1
            visible = self._visible_candidates(candidates)
            target = min(cursor, len(visible) - 1)
            self.setCandidateList(visible)
        elif key_code == VK_DOWN:
            if cursor + 1 < len(visible):
                target = cursor + 1
            elif self.candidate_page < last_page:
                self.candidate_page += 1
                visible = self._visible_candidates(candidates)
                target = 0
                self.setCandidateList(visible)
        elif key_code == VK_UP:
            if cursor > 0:
                target = cursor - 1
            elif self.candidate_page > 0:
                self.candidate_page -= 1
                visible = self._visible_candidates(candidates)
                target = len(visible) - 1
                self.setCandidateList(visible)
        self.setCandidateCursor(max(0, min(len(visible) - 1, target)))
        self._render_buffer(keep_candidates=True)

    def _choose_highlighted_candidate(self, index: int) -> None:
        candidates, _ = self._candidate_target()
        index = self._absolute_candidate_index(index)
        if index < 0 or index >= len(candidates):
            self._bell("沒有這個候選字")
            return
        if self.reading_open and self.session.candidates:
            selected = candidates[index]
            if self._is_literal_bopomofo(selected):
                self._emit_or_buffer_literal(selected)
                return
            self.feedback_store.record(
                [self.session.preedit], candidates[0], selected
            )
            self.session.pins.pin(self.session.preedit, selected)
            self.session.refresh_candidates()
            self._accept_active_candidate(0, advance_focus=True)
            return
        if not self.candidate_choices:
            return
        self._apply_candidate_choice(self.candidate_choices[index])
        self.setShowCandidates(False)
        self._render_buffer()

    def _apply_candidate_choice(self, choice: CandidateChoice) -> None:
        if self._is_literal_bopomofo(choice.text):
            if choice.start == 0 and choice.end == len(self.segments):
                # Preserve the established standalone behavior: choosing raw
                # Zhuyin with no surrounding editable text commits it at once.
                self.setCommitString(choice.text)
                self._clear_all()
                self.setCompositionString("")
                self.setCompositionCursor(0)
            else:
                self._buffer_literal_text(choice.text, choice.start, choice.end)
            return
        readings = [
            segment.reading for segment in self.segments[choice.start : choice.end]
        ]
        converted = "".join(
            segment.text for segment in self.segments[choice.start : choice.end]
        )
        self.feedback_store.record(readings, converted, choice.text)
        if choice.width == 1:
            self.session.pins.pin(readings[0], choice.text)
        else:
            self.phrase_store.learn(readings, choice.text)
        for segment, selected in zip(
            self.segments[choice.start : choice.end], choice.text
        ):
            segment.candidates = list(
                dict.fromkeys([selected] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            segment.locked = True
        # Move past the chosen word. The next character to the right becomes
        # the next edit target, just like a single-character selection.
        self.focus_index = choice.end - 1

    def _pin_highlighted_candidate(self) -> None:
        candidates, _ = self._candidate_target()
        index = self._absolute_candidate_index(self.candidateCursor)
        if index < 0 or index >= len(candidates):
            self._bell("沒有可固定的候選字")
            return
        selected = candidates[index]
        if self.reading_open and self.session.candidates:
            self.feedback_store.record(
                [self.session.preedit], self.session.candidates[0], selected
            )
            self.session.pins.pin(self.session.preedit, selected)
            self.session.refresh_candidates()
        else:
            if not self.candidate_choices:
                self._bell("沒有可固定的候選字")
                return
            choice = self.candidate_choices[index]
            self._apply_candidate_choice(choice)
            self.candidate_choices = [choice] + [
                candidate
                for offset, candidate in enumerate(self.candidate_choices)
                if offset != index
            ]
        self.candidate_page = 0
        self.setCandidateCursor(0)
        self._render_buffer(keep_candidates=True)
        self.showMessage("已固定為這組注音的第一候選", 2)

    def _handle_session_event(self, event: Event) -> None:
        if event.kind is EventKind.UPDATED and self.session.candidates:
            # libchewing can append extremely rare Han characters even for a
            # symbol that is not a normal standalone syllable (for example a
            # lone ㄑ). Its ranked first candidate is the reliable boundary:
            # Chinese first means auto-accept it; literal Zhuyin first means
            # show the menu and do not let an obscure tail candidate win.
            if self._is_literal_bopomofo(self.session.candidates[0]):
                self.reading_open = True
                self.candidate_page = 0
                self.setCandidateList(
                    self._visible_candidates(self.session.candidates)
                )
                self.setCandidateCursor(0)
                self.setShowCandidates(True)
                self._render_buffer(keep_candidates=True)
                return
            self._accept_active_candidate(0)
            return
        self._render_event(event)

    def _accept_active_candidate(self, index: int, advance_focus: bool = False) -> None:
        if not self.session.candidates or not 0 <= index < len(self.session.candidates):
            self._bell("沒有這個候選字")
            return
        reading = self.session.preedit
        segment = BufferedSyllable(
            reading=reading,
            candidates=list(self.session.candidates),
            selected=index,
            # A stored single-character preference remains candidate zero for
            # isolated input, but must not become a permanent context lock.
            # Otherwise an old 仙/不 preference blocks the reliable phrase
            # correction 你先開始下一步吧. A choice made explicitly in this
            # composition still arrives with advance_focus=True and is locked.
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
        """Decode every unlocked span, then apply whole-sentence correction."""
        if len(self.segments) < 2:
            return
        self._apply_phrase_lattice()
        whole_options = self._ranked_phrase_options(0, len(self.segments))
        whole_default = whole_options[0] if whole_options else ""
        if whole_default:
            self._apply_ranked_phrase(len(self.segments), whole_default)

    def _apply_phrase_lattice(self) -> None:
        """Compose one sentence from multiple exact-reading common words."""
        readings = [segment.reading for segment in self.segments]
        current_text = "".join(segment.text for segment in self.segments)
        protected = [segment.locked for segment in self.segments]
        spans = decode_phrase_lattice(
            readings,
            current_text,
            protected,
            self.session.lexical_phrase_candidates,
            self.session.phrase_weight,
            self.phrase_store.exact,
            MAX_PHRASE_LENGTH,
        )
        for span in spans:
            for segment, character in zip(
                self.segments[span.start : span.end], span.text
            ):
                if segment.locked:
                    continue
                segment.candidates = list(
                    dict.fromkeys([character] + segment.candidates)
                )[: self.session.max_candidates]
                segment.selected = 0
                if span.personal:
                    segment.locked = True

    def _apply_ranked_phrase(
        self, width: int, phrase: str, lock: bool = False
    ) -> None:
        """Move one phrase to the front without replacing locked segments."""
        if width < 1 or len(phrase) != width or width > len(self.segments):
            return
        for segment, suggested in zip(self.segments[-width:], phrase):
            if segment.locked:
                continue
            segment.candidates = list(
                dict.fromkeys([suggested] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            if lock:
                segment.locked = True

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
            candidate_index = self._absolute_candidate_index(self.candidateCursor)
            if candidates and 0 <= candidate_index < len(candidates):
                preview = candidates[candidate_index]
                if self.reading_open and self.session.candidates:
                    active_text = preview
                elif self.candidate_choices:
                    choice = self.candidate_choices[candidate_index]
                    segment_texts[choice.start : choice.end] = list(choice.text)
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
            self.candidate_page = 0
            self.candidate_choices = []
            self.setCandidateList([])
            self.setShowCandidates(False)
            self.setCandidateCursor(0)

    def _commit_buffer(self, suffix: str = "") -> None:
        # Space, Enter, punctuation, Shift, deactivation, and direct English
        # insertion all commit through here. Re-apply the shared default so a
        # correct candidate cannot remain hidden behind Down at send time.
        self._apply_phrase_ranking()
        text = "".join(segment.text for segment in self.segments)
        if not text:
            self._bell("沒有可以送出的文字")
            return
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
        self.candidate_page = 0
        self.candidate_choices = []
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
