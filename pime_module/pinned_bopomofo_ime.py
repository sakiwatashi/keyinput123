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
from .bopomofo_core.context_store import ContextStore
from .bopomofo_core.feedback_store import FeedbackStore
from .bopomofo_core.hidden_characters import (
    shared_hidden_characters as HIDDEN_CHARACTERS,
)
from .bopomofo_core.keymap import is_typable_reading, load_layout, symbol_for_event
from .bopomofo_core.libchewing_provider import LibChewingProvider
from .bopomofo_core.phrase_decoder import decode_phrase_lattice
from .bopomofo_core.usage_store import UsageStore
from .bopomofo_core.word_usage import WordUsageStore
from .bopomofo_core.phrase_store import (
    MAX_PHRASE_LENGTH,
    MIN_PHRASE_LENGTH,
    PhraseStore,
)
from .bopomofo_core.phonetic_corrector import PhoneticCorrector
from .bopomofo_core.pinned_store import PinnedStore
from .bopomofo_core.request_trace import shared_trace as request_trace
from .bopomofo_core.session import CandidateSession
from .bopomofo_core.state import (
    INITIALS,
    MEDIALS,
    RIMES,
    SLOT_ORDER,
    TONES,
    Event,
    EventKind,
    slot_for,
)


VK_OEM_QUOTE = 0xDE
VK_OEM_SEMICOLON = 0xBA
VK_OEM_COMMA = 0xBC
VK_OEM_PERIOD = 0xBE
VK_OEM_SLASH = 0xBF
VK_OEM_LBRACKET = 0xDB
VK_OEM_RBRACKET = 0xDD

# Microsoft Bopomofo puts Chinese punctuation on Ctrl and leaves Shift for
# plain ASCII. Binding punctuation to Shift instead made one physical key mean
# two different things depending on mode: Shift+, produced 「，」 while composing
# but 「<」 once the same Shift had toggled English, which is the inconsistency
# this table exists to remove.
#
# These apply in Chinese and English mode alike -- being usable without
# switching modes is the point of the Ctrl convention.
#
# Deliberate departure from Microsoft: 「」 sits on Ctrl+[ ] where Microsoft
# puts 【】. 「」 is the primary quotation mark in Traditional Chinese and 【】
# is comparatively rare, so the common case gets the shorter chord and the
# nested quotes 『』 take Ctrl+Shift.
# What a shifted non-letter key stands for when the host supplies no charCode.
# charCode is preferred because it follows the active keyboard layout, but
# without a fallback the key would drop through to the Bopomofo table and a
# shifted punctuation key would insert a Bopomofo symbol instead of a symbol.
SHIFTED_ASCII_FALLBACK = {
    0x20: " ",
    0x31: "!", 0x32: "@", 0x33: "#", 0x34: "$", 0x35: "%",
    0x36: "^", 0x37: "&", 0x38: "*", 0x39: "(", 0x30: ")",
    VK_OEM_SEMICOLON: ":",
    0xBB: "+",
    VK_OEM_COMMA: "<",
    0xBD: "_",
    VK_OEM_PERIOD: ">",
    VK_OEM_SLASH: "?",
    0xC0: "~",
    VK_OEM_LBRACKET: "{",
    0xDC: "|",
    VK_OEM_RBRACKET: "}",
    VK_OEM_QUOTE: '"',
}

# TSF delivers a preserved key through ITfKeyStrokeMgr rather than the key
# event sink. Defined here rather than imported so the module still loads on a
# PIME build whose textService.py predates preserved-key support.
TF_MOD_ON_KEYUP = 0x0200
# Ours alone. Changing it would orphan the registration TSF already holds.
SHIFT_TOGGLE_GUID = "f02200cc-713f-451d-8df5-56856e48d191"
CTRL_PUNCTUATION = {
    (VK_OEM_COMMA, False): "，",
    (VK_OEM_PERIOD, False): "。",
    (VK_OEM_QUOTE, False): "、",
    (VK_OEM_SEMICOLON, False): "；",
    (VK_OEM_SEMICOLON, True): "：",
    (VK_OEM_SLASH, True): "？",
    (0x31, True): "！",
    (VK_OEM_LBRACKET, False): "「",
    (VK_OEM_RBRACKET, False): "」",
    (VK_OEM_LBRACKET, True): "『",
    (VK_OEM_RBRACKET, True): "』",
}
# 你自己用過一次值多少詞庫權重。詞庫權重的量級是 0 到二十萬，一步(5813) 對
# 一部(21778) 差一萬六，所以八次左右能翻過來——夠快到有感，又不會第一次就
# 搶走一個常用詞。
WORD_USE_BONUS = 2000
# 用過幾次才算習慣。一次跟隨手送出的錯字分不開——個人偏好無條件覆寫詞庫，
# 正是「部要」「下一不」那一類問題的來源。
WORD_USE_CONFIDENCE = 3
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
    # True only when the user explicitly chose this segment's text. Commit
    # uses it to tell a hand-corrected composition apart from the engine's
    # own guesses, which must never teach the personal lexicon.
    user_corrected: bool = False

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
        # 自訂鍵位。無效或壞掉的配置會退回內建大千：寧可鍵位跟使用者預期不同，
        # 也不要因為改壞一個檔案就完全打不出中文。這裡不回報原因——輸入法沒有
        # 可以說話的地方，而按鍵追蹤預設是關的。負責解釋的是控制台的「按鍵配置」
        # 分頁，它在存檔前就會驗，也會在開啟時說明目前這份配置有什麼問題。
        load_layout()
        provider = LibChewingProvider(pinned_libchewing)
        self.session = CandidateSession(provider, PinnedStore(pin_path))
        self.phrase_store = PhraseStore(phrase_path)
        # 使用次數獨立存放。統計檔壞掉或不見只損失統計，phrases.json 那 288 筆
        # 不可取代的資料完全不受影響——這是刻意不改主檔格式的理由。
        self.usage_store = UsageStore(
            os.path.join(appdata, "PinnedBopomofo", "usage.json")
        )
        self.feedback_store = FeedbackStore(feedback_path)
        # 「這個讀音接在哪個字後面時你選了什麼」。跟 usage.json 一樣獨立存放：
        # phrases.json 是不可取代的資料，改它的格式就要背一個遷移，而這個檔
        # 壞掉或不見只讓選字退回原本的行為。
        self.context_store = ContextStore(
            os.path.join(appdata, "PinnedBopomofo", "contexts.json")
        )
        # 你自己的詞頻表。字的層級分不出「不」和「步」，詞的層級（不要／
        # 下一步）根本沒有歧義——讀音串不同，不會互相干擾。
        self.word_usage = WordUsageStore(
            os.path.join(appdata, "PinnedBopomofo", "word_usage.json")
        )
        self.autocorrector = Autocorrector()
        self.phonetic_corrector = PhoneticCorrector(MAX_PHRASE_LENGTH)
        self.english_mode = False
        self.last_key_event = None
        self.last_key_down_time = 0.0
        self.pending_shift_toggle = False
        # Set once TSF has actually delivered the preserved key. Two routes
        # reporting one release would toggle twice and look like nothing
        # happening — the exact symptom this was written to fix — so the
        # fallback stands down as soon as the better route proves itself.
        self.shift_preserved_key_seen = False
        # 目前按著沒放的實體鍵。用來認出鍵盤自動重複：Windows 會在按住時
        # 一直送 key down 而中間沒有 key up，那是同一次擊鍵，不是使用者
        # 又打了一次。
        self.held_key_code = None

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
        # Off unless the user turns it on. Records which callbacks arrive, not
        # what was typed -- see bopomofo_core/request_trace.py.
        request_trace.record(msg, reply, {
            "english_mode": self.english_mode,
            "keyboard_open": self.keyboardOpen,
        })
        try:
            self._apply_beacon_mode(reply)
        except Exception:
            # This runs on every key event and only shrinks a window. Like the
            # rest of the mirror it is cosmetic, so a failure here must leave
            # the reply exactly as the input method built it rather than take
            # the keystroke down with it.
            pass
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
        # Connect before the user can compose anything. Beacon mode needs a
        # live connection, so without this the first candidate page of every
        # session is drawn by PIME's own window instead.
        try:
            self.candidate_ui.warm_up()
        except Exception:
            pass
        self.setSelKeys(CANDIDATE_SELECTION_LABELS)
        self.customizeUI(
            candFontName="Microsoft JhengHei UI",
            candFontSize=16,
            candPerRow=CANDIDATES_PER_ROW,
            candUseCursor=True,
        )
        # Ask TSF itself to watch for a Shift release. Preserved keys travel a
        # different route from ordinary key events, and that route survives
        # places where the key-up sink does not: console windows, and remote
        # desktop clients such as AnyDesk that grab the keyboard and forward it
        # elsewhere. Microsoft Bopomofo switches language fine in exactly those
        # places, which is the evidence that this route is the one that works.
        # filterKeyUp stays as the fallback for hosts that never deliver it.
        try:
            self.addPreservedKey(VK_SHIFT, TF_MOD_ON_KEYUP, SHIFT_TOGGLE_GUID)
        except Exception:
            # An older PIME without preserved-key support must not stop the
            # input method from loading; the fallback still works there.
            pass

    def setCommitString(self, text):
        """所有送出的文字都經過這裡，所以計數只需要掛這一個點。

        程式裡有四處呼叫它（一般提交、直接送出注音、單一候選、游標插入），
        在四處各插一行計數，遲早會漏掉新增的第五處。
        """
        try:
            self.usage_store.record(text)
        except Exception:
            # 統計絕不能擋住送字。壞掉就安靜跳過。
            pass
        return super().setCommitString(text)

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
        # Usage counts are buffered, so the last few commits are still only in
        # memory when the profile goes away. Write them out here.
        try:
            self.usage_store.flush()
            self.word_usage.flush()
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
        # Never catch up on a Shift press. That press is about to arm a release
        # of its own, so consuming here made a single tap toggle twice and land
        # back where it started. Measured: with a release still outstanding, one
        # tap produced no visible change at all.
        if self.pending_shift_toggle and not self._is_shift_key(keyEvent.keyCode):
            # onKeyUp never arrived. Measured inside an AnyDesk session: one
            # Shift release produces two filterKeyUp calls and no onKeyUp at
            # all, so the toggle -- which lives in onKeyUp because that is
            # where a TSF edit session exists -- simply never ran. Catch up
            # here, on the next key, rather than lose the release.
            if self.isComposing():
                # Toggling has to commit the composition, and that needs the
                # edit session only onKeyDown gets. Claim this key so
                # onKeyDown runs and can finish the job properly.
                return True
            self.pending_shift_toggle = False
            self.english_mode = not self.english_mode
        self.last_key_event = keyEvent
        # A Shift press always restamps the clock, because that clock exists to
        # time this very press. Only the first key of a chord stamps it
        # otherwise, so that holding Shift and typing a letter still measures
        # the Shift.
        #
        # The old rule stamped only when the clock was zero, and the clock is
        # zeroed in filterKeyUp. A key whose release never arrives therefore
        # froze it: UAC's secure desktop takes the whole desktop away mid-press
        # without ever sending onDeactivate, so the release is simply lost and
        # the stale timestamp then failed the 0.5s test for the next real Shift
        # tap -- the user pressed Shift, nothing happened, and it looked broken.
        if self._is_shift_key(keyEvent.keyCode) or self.last_key_down_time == 0.0:
            self.last_key_down_time = time.time()
        if keyEvent.isKeyDown(VK_MENU):
            return False
        # Ahead of the English-mode passthrough on purpose: Ctrl punctuation is
        # meant to work in both modes.
        if self._ctrl_punctuation(keyEvent) is not None:
            return True
        if keyEvent.isKeyDown(VK_CONTROL):
            return self.showCandidates and keyEvent.keyCode == VK_PRIOR
        if self.english_mode:
            return False
        if self._numpad_text(keyEvent) is not None:
            return True
        if self.showCandidates and self._candidate_number(keyEvent) is not None:
            return True
        if self._temporary_english_letter(keyEvent) is not None:
            return True
        if self._shift_ascii(keyEvent) is not None:
            return True
        if keyEvent.keyCode == VK_SPACE:
            return self.isComposing()
        if self.showCandidates and keyEvent.keyCode in (
            VK_UP,
            VK_DOWN,
            VK_LEFT,
            VK_RIGHT,
            VK_PRIOR,
            VK_NEXT,
        ):
            return True
        if keyEvent.keyCode == VK_DOWN:
            return self._has_candidate_target()
        if keyEvent.keyCode in (VK_LEFT, VK_RIGHT):
            return bool(self.segments) and not self.session.preedit
        if keyEvent.keyCode in (VK_RETURN, VK_BACK, VK_ESCAPE, VK_DELETE):
            return self.isComposing()
        if symbol_for_event(keyEvent.keyCode, keyEvent.charCode) is not None:
            return True
        # A key carrying no Bopomofo is ours only while something is being
        # composed. With an empty buffer the application receives it in the
        # right place already, so claiming it would change behaviour for no
        # gain.
        return self.isComposing() and self._unmapped_ascii(keyEvent) is not None

    def onKeyDown(self, keyEvent):
        if self.pending_shift_toggle:
            # The release filterKeyDown deferred here because a composition
            # was open. This callback has the edit session, so the toggle can
            # commit before the key that arrived is handled in the new mode.
            self.pending_shift_toggle = False
            self._toggle_language_mode()
        # Mirrors filterKeyDown: ahead of the English-mode passthrough so the
        # Ctrl punctuation shortcuts work in both modes.
        ctrl_punctuation = self._ctrl_punctuation(keyEvent)
        if ctrl_punctuation is not None:
            self._emit_punctuation(ctrl_punctuation)
            return True
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

        english_letter = self._temporary_english_letter(keyEvent)
        if english_letter is not None:
            self._emit_temporary_english(english_letter)
            return True

        shifted_ascii = self._shift_ascii(keyEvent)
        if shifted_ascii is not None:
            self._emit_punctuation(shifted_ascii)
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
            VK_PRIOR,
            VK_NEXT,
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
                    # A first tone the session refuses outright. The raw
                    # Zhuyin is what the user asked for.
                    self._emit_or_buffer_literal(self.session.preedit)
                    return True
                if self.session.candidates and self._is_literal_bopomofo(
                    self.session.candidates[0]
                ):
                    # Space supplied the tone and the dictionary ranked the raw
                    # Zhuyin first, which is it saying this reading has no real
                    # Chinese syllable. Emit it on the space itself, as
                    # Microsoft Bopomofo does -- that is what makes ㄏ+space
                    # repeatable at typing speed. A menu here cost a keystroke
                    # and swallowed input: with it open, retyping ㄏ only
                    # replaced the initial with itself, so ㄏ空ㄏ空ㄏ空 produced
                    # a single ㄏ.
                    #
                    # Rare Han characters trailing the literal (ㄑ→胠, ㄟ→欸,
                    # ㄦ→児) do not change this. The menu existed to stop one of
                    # those winning by accident, and emitting the literal serves
                    # that better than offering them. They lose their route in
                    # through this key, which is the accepted cost of ㄏ, ㄑ and
                    # ㄦ all behaving alike.
                    #
                    # This lives here rather than in _handle_session_event
                    # because a tone the user typed explicitly is a different
                    # act: ㄢ˙ also has only the literal, and its menu is how
                    # Microsoft lets a deliberate phonetic spelling be chosen.
                    self._emit_or_buffer_literal(self.session.candidates[0])
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

        if keyEvent.keyCode == VK_DELETE:
            if not self.isComposing():
                return False
            # 刪游標右邊那一格。游標畫在 focus_index 之後，所以右邊是它 +1。
            #
            # 沒有這一段的時候 Del 根本沒被認領，按鍵直接交給應用程式：畫面上
            # 的字消失了，而輸入法的 segments 一格都沒少。下一次重繪就把它畫
            # 回來——使用者看到的是「刪掉的字又自己跑出來」。
            index = (
                self.focus_index + 1 if self.focus_index is not None else len(self.segments)
            )
            if not 0 <= index < len(self.segments):
                self._bell("游標右邊沒有可以刪除的文字")
                return True
            self.segments.pop(index)
            # 跟 Backspace 一樣，把缺口留成下一個注音的插入點，不要讓它跑到最右邊。
            self.replacement_index = index
            self.reading_open = False
            if not self.segments:
                self.focus_index = None
            else:
                self.focus_index = min(self.focus_index or 0, len(self.segments) - 1)
            self._apply_phrase_ranking()
            self._render_buffer()
            return True

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
            repeating = self.held_key_code == keyEvent.keyCode
            self.held_key_code = keyEvent.keyCode
            carry = self._carry_into_new_syllable(symbol, repeating)
            if carry is not None:
                self._close_syllable_before(carry)
            if symbol in TONES and not self.session.preedit:
                self._emit_or_buffer_literal(symbol)
                return True
            # Typing follows the caret. This used to force the caret back to
            # the end unless Backspace had left an explicit gap, so moving left
            # and typing without deleting appended instead of inserting:
            # 我們|好 became 我們好大. focus_index already tracks the caret
            # after arrow keys, candidate selection and each insertion, so
            # there is nothing here to correct.
            event = self.session.input_symbol(symbol)
            self.reading_open = False
            self._handle_session_event(event)
            return True

        unmapped = self._unmapped_ascii(keyEvent)
        if unmapped is not None and self.isComposing():
            self._emit_or_buffer_literal(unmapped)
            return True
        return False

    def filterKeyUp(self, keyEvent):
        if self.held_key_code == keyEvent.keyCode:
            self.held_key_code = None
        if self.shift_preserved_key_seen:
            # TSF is reporting Shift releases as a preserved key, so handling
            # them here as well would cancel out. TSF is documented to consume
            # a preserved key rather than pass it to the key sink, but this
            # does not depend on that being true everywhere.
            self.last_key_down_time = 0.0
            return False
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

    def onPreservedKey(self, guid):
        """TSF reporting the Shift release it was asked to watch for.

        This is the route that keeps working inside console windows and remote
        desktop clients, where the key-up sink does not reach us.
        """
        if guid.lower() != SHIFT_TOGGLE_GUID:
            return False
        self.shift_preserved_key_seen = True
        self.pending_shift_toggle = False
        self.last_key_down_time = 0.0
        self._toggle_language_mode()
        return True

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

    @staticmethod
    def _shift_held(keyEvent) -> bool:
        return any(
            keyEvent.isKeyDown(code) for code in (VK_SHIFT, 0xA0, 0xA1)
        )

    def _ctrl_punctuation(self, keyEvent) -> str | None:
        """Chinese punctuation, following Microsoft Bopomofo's Ctrl convention.

        Callers must consult this before any English-mode passthrough: these
        shortcuts are meant to work without switching modes.
        """
        if not keyEvent.isKeyDown(VK_CONTROL):
            return None
        return CTRL_PUNCTUATION.get(
            (keyEvent.keyCode, self._shift_held(keyEvent))
        )

    def _shift_ascii(self, keyEvent) -> str | None:
        """The plain ASCII character a shifted non-letter key stands for.

        Emitted here rather than passed through to the application, because a
        pending composition has to commit first; letting the raw character
        reach the application while an uncommitted buffer is still displayed
        would insert it in the wrong place.

        Letters are excluded: Shift+A-Z is the separate temporary-English
        interaction, which emits one English letter without changing mode.
        """
        if not self._shift_held(keyEvent):
            return None
        if 0x41 <= keyEvent.keyCode <= 0x5A:
            return None
        # charCode already reflects the active keyboard layout, so it is
        # preferred; the table only covers hosts that supply none.
        if 0x20 <= keyEvent.charCode <= 0x7E:
            return chr(keyEvent.charCode)
        return SHIFTED_ASCII_FALLBACK.get(keyEvent.keyCode)

    def _unmapped_ascii(self, keyEvent) -> str | None:
        """The character on a key that carries no Bopomofo symbol.

        Six keys on a standard board have no Bopomofo on them -- ``'``, ``=``,
        ``[``, ``]``, ``\\`` and ``` ` ``` -- and a custom layout can free up
        more, so the set is derived rather than listed.

        Left unclaimed, these fall through to the application while the
        composition is still on screen, and the character lands after the whole
        buffer instead of at the caret: typing ``'`` at 我們|好 put it at the
        far right rather than between 們 and 好.

        That is the reasoning ``_shift_ascii`` already documents. It was only
        ever applied to the shifted half, which is why ``Shift+'`` inserted a
        quotation mark at the caret correctly while a bare ``'`` did not.
        """
        if self._shift_held(keyEvent):
            return None
        if symbol_for_event(keyEvent.keyCode, keyEvent.charCode) is not None:
            return None
        # charCode already reflects the active keyboard layout. No fallback
        # table here on purpose: without a charCode there is no way to know
        # what an unmapped key prints, and guessing would type the wrong
        # character rather than the nothing it types today.
        if 0x20 <= keyEvent.charCode <= 0x7E:
            return chr(keyEvent.charCode)
        return None

    def _temporary_english_letter(self, keyEvent) -> str | None:
        """Return the ASCII letter produced by Shift+A-Z.

        A standalone Shift press still toggles Chinese/English mode.  Holding
        Shift while pressing a letter is a separate, protected interaction:
        it emits one temporary English letter without changing modes.

        The case follows the keyboard rather than being forced to uppercase.
        Shift inverts Caps Lock everywhere else in Windows, so with Caps Lock
        on, Shift+A must produce a lowercase letter; always returning
        uppercase made this the one place where that stopped being true.
        """
        if not self._shift_held(keyEvent):
            return None
        if not (0x41 <= keyEvent.keyCode <= 0x5A):
            return None
        # charCode is what Windows already resolved from the full keyboard
        # state, so it honours Caps Lock and non-US layouts for free.
        if 0x41 <= keyEvent.charCode <= 0x5A or 0x61 <= keyEvent.charCode <= 0x7A:
            return chr(keyEvent.charCode)
        letter = chr(keyEvent.keyCode)
        return letter.lower() if keyEvent.isKeyToggled(VK_CAPITAL) else letter

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
        # Every caller ends up asking libchewing about these readings, and a
        # literal ASCII segment has none it can answer for. _apply_phrase_ranking
        # already splits the buffer at those, but _build_candidate_choices picks
        # its own spans -- pressing Down with the caret near a 我們=好 crossed
        # one and raised straight out of onKeyDown, losing the whole composition.
        # Guarding the shared entry point covers both, and any span chosen later.
        if not all(
            is_typable_reading(segment.reading)
            for segment in self.segments[start:end]
        ):
            return []
        readings = [segment.reading for segment in self.segments[start:end]]
        context = self.segments[start - 1].text[-1] if start > 0 else ""
        personal, _contextual = self._personal_phrase(readings, context)
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
                self._weighted_phrase,
                self._personal_phrase,
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
                + self._favoured_words(readings)
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
        """Navigate a ten-item, two-column page without letter labels.

        The window paints a vertical-first grid: labels 1-5 run down the left
        column and 6-0 down the right, so Right/Left hop between the columns
        of the same row, as in Microsoft Bopomofo's expanded grid. They turn
        the page only when leaving the grid at its outer column, keeping the
        row. PageDown/PageUp always turn pages and land on the first cell.
        Down/Up walk the page linearly and roll over at its edges.
        """
        candidates, _ = self._candidate_target()
        if not candidates:
            return
        visible = self._visible_candidates(candidates)
        cursor = min(self.candidateCursor, len(visible) - 1)
        column_height = CANDIDATE_PAGE_SIZE // 2

        last_page = max(0, (len(candidates) - 1) // CANDIDATE_PAGE_SIZE)
        target = cursor
        if key_code == VK_RIGHT:
            if cursor < column_height and cursor + column_height < len(visible):
                # Same row, right column: 1 hops to 6 instead of paging.
                target = cursor + column_height
            elif self.candidate_page < last_page:
                self.candidate_page += 1
                visible = self._visible_candidates(candidates)
                # Landing from the right column keeps the row on the new page.
                target = cursor - column_height if cursor >= column_height else cursor
                self.setCandidateList(visible)
        elif key_code == VK_LEFT:
            if cursor >= column_height:
                target = cursor - column_height
            elif self.candidate_page > 0:
                self.candidate_page -= 1
                visible = self._visible_candidates(candidates)
                # Pages before the last are always full, so the same row of
                # the right column exists.
                target = cursor + column_height
                self.setCandidateList(visible)
        elif key_code == VK_NEXT:
            if self.candidate_page < last_page:
                self.candidate_page += 1
                visible = self._visible_candidates(candidates)
                target = 0
                self.setCandidateList(visible)
        elif key_code == VK_PRIOR:
            if self.candidate_page > 0:
                self.candidate_page -= 1
                visible = self._visible_candidates(candidates)
                target = 0
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
        self._forget_conflicting_phrases(choice.start, choice.end, choice.text)
        if choice.width == 1:
            self.session.pins.pin(readings[0], choice.text)
        else:
            self.phrase_store.learn(readings, choice.text)
            # 選字是使用者最明確的表態，連同左鄰字一起記下來。
            self._learn_context(choice.start, choice.end, choice.text)
        for segment, selected in zip(
            self.segments[choice.start : choice.end], choice.text
        ):
            segment.candidates = list(
                dict.fromkeys([selected] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            segment.locked = True
            segment.user_corrected = True
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
            user_corrected=advance_focus,
        )
        # The caret has to decide where this goes. Only Backspace used to be
        # honoured here, so moving left and typing without deleting appended to
        # the end instead: 我們好 with the caret at 我們|好 became 我們好大.
        # focus_index + 1 is the caret, and it holds -1 when the caret sits
        # before the first segment, which inserts at the front.
        # _buffer_literal_text already resolved the position this way.
        if self.replacement_index is not None:
            insertion = self.replacement_index
        elif self.focus_index is not None:
            insertion = self.focus_index + 1
        else:
            insertion = len(self.segments)
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

    def _carry_into_new_syllable(
        self, symbol: str, repeating: bool = False
    ) -> list[str] | None:
        """Whether this symbol starts a new syllable, and what comes with it.

        Returns None to keep editing the current syllable, otherwise the
        components already typed that belong to the *new* one.

        Two identical key sequences have to be told apart:

            ㄧ ㄒ ㄣ ˋ    -> 信      one syllable, typed out of order
            ㄧ ㄅ ㄨ ˋ    -> 一步    two syllables, typed straight through

        Both start with a medial and continue with an initial, so the initial
        cannot be the signal. An earlier version split there and broke
        out-of-order input, which this user relies on daily.

        The signal is *replacement*. Filling an empty slot is free-order input
        and always merges. Overwriting a slot that is already filled means the
        component being overwritten belonged to a syllable the user has already
        finished: ㄨ landing on the ㄧ of 一 is the moment 一 is revealed to be
        its own syllable. Two exceptions:

        * Re-typing the slot that was just edited, with a different symbol, is
          somebody fixing a typo, and keeps editing this syllable.
        * Re-typing it with the *same* symbol fixes nothing, so it is not a fix.
          ㄧ after ㄧ is 一 followed by another syllable (一樣).

        What carries over: components edited after the overwritten slot that
        sit earlier in the syllable. In 一步 the ㄅ was typed after the ㄧ but
        belongs in front of it, so 一 commits alone and ㄅ starts the new
        syllable. In 因為 the ㄣ was typed after the ㄧ and belongs behind it,
        so 因 commits whole and nothing carries.
        """
        slot = slot_for(symbol)
        if slot is None or slot == "tone":
            return None
        if repeating:
            # 鍵盤自動重複是同一次擊鍵。少了這一條，按住 ㄧ 不放會一路送出
            # 「一一一一一」——每次重複都被當成「又打了一個一」。
            return None
        slots = self.session.editor.slots
        if slot not in slots:
            # 填空位。照順序往後填不必多問；只有填到已填欄位「前面」時，才需要
            # 確認合出來的東西是不是真的存在——ㄍ 併到待決的 ㄧ 上會得到 ㄍㄧ，
            # 而國語沒有這個組合，「一個」因此變成 ㄍㄧㄜˋ。
            if any(
                SLOT_ORDER.index(name) > SLOT_ORDER.index(slot) for name in slots
            ):
                merged = dict(slots)
                merged[slot] = symbol
                spelling = "".join(
                    merged.get(name, "") for name in SLOT_ORDER
                )
                if not self.session.prefix_has_candidates(spelling):
                    return []
            return None
        order = self.session.editor.edit_order
        if order and order[-1] == slot and slots[slot] != symbol:
            return None
        position = order.index(slot) if slot in order else len(order)
        return [
            slots[name]
            for name in order[position + 1 :]
            if SLOT_ORDER.index(name) < SLOT_ORDER.index(slot)
        ]

    def _close_syllable_before(self, carry: list[str]) -> bool:
        """Commit what is pending minus ``carry``, as first tone.

        Returns False and puts the editor back exactly as it was when that
        cannot produce a real character. A partial spelling has to stay
        completable, so the caller falls back to merging rather than eating the
        keystroke.
        """
        slots = self.session.editor.slots
        keeping = [value for value in slots.values() if value not in carry]
        if not keeping:
            return False

        def in_slot_order(values):
            return sorted(values, key=lambda value: SLOT_ORDER.index(slot_for(value)))

        self.session.clear()
        for value in in_slot_order(keeping):
            self.session.input_symbol(value)
        if not any(value in TONES for value in keeping):
            self.session.input_symbol("ˉ")

        if not self.session.candidates or self._is_literal_bopomofo(
            self.session.candidates[0]
        ):
            self.session.clear()
            for value in in_slot_order(slots.values()):
                self.session.input_symbol(value)
            return False

        self._accept_active_candidate(0)
        for value in carry:
            self.session.input_symbol(value)
        return True

    def _forget_conflicting_phrases(self, start: int, end: int, text: str) -> None:
        """把跟這次選擇牴觸的個人詞條丟掉。

        使用者明確選了別的字，就等於說「蓋在這裡的那筆記錄是錯的」。不丟掉的話
        它下一次組字又會贏回來，而使用者的修正只會落在 pins.json（單字）或另一個
        讀音鍵上，永遠碰不到病灶——實測就是這樣一直來回選「不」和「步」。

        掃過每一個涵蓋這次選擇、寬度在詞庫範圍內的跨度。最多 12x12 次字典查詢，
        而且只在使用者親手選字時才跑。
        """
        for span_start in range(max(0, end - MAX_PHRASE_LENGTH), start + 1):
            for span_end in range(
                max(span_start + MIN_PHRASE_LENGTH, end),
                min(len(self.segments), span_start + MAX_PHRASE_LENGTH) + 1,
            ):
                readings = [
                    segment.reading
                    for segment in self.segments[span_start:span_end]
                ]
                remembered = self.phrase_store.exact(readings)
                if not remembered:
                    continue
                # 只怪罪畫面上這段文字真正的來源。
                #
                # 第一版只要條目在被改的位置上跟新選擇不同就刪，於是使用者在
                # 別的詞裡選一個字，會連帶刪掉一個剛好涵蓋同一段讀音、但跟畫面
                # 無關的條目。實測損失了 `ㄧˉ ㄅㄨˋ -> 一步`：使用者在某處選了
                # 「不」，而那筆條目當時根本沒有參與組字。
                current = "".join(
                    segment.text
                    for segment in self.segments[span_start:span_end]
                )
                if remembered != current:
                    continue
                chosen = remembered[start - span_start : end - span_start]
                if chosen != text:
                    self.phrase_store.forget(readings)

    def _favoured_words(self, readings: list[str]) -> list[str]:
        """你自己用得夠多的詞，排在詞庫前面。

        用過一次不算——那跟隨手送出的錯字分不開，而個人偏好無條件覆寫詞庫正是
        「部要」「下一不」那一類問題的來源。要連續用到 WORD_USE_CONFIDENCE 次，
        而且是這段讀音底下用得最多的那個，才排到前面。

        這是詞的層級，所以沒有同音歧義：「不要」和「下一步」的讀音串不同，各自
        累積，不會互相干擾。字的層級做不到這件事。
        """
        counts = self.word_usage.words_for(readings)
        if not counts:
            return []
        word, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        if count < WORD_USE_CONFIDENCE:
            return []
        return [word]

    def _record_word_usage(self) -> None:
        """把這次送出的文字切成已知的詞，每個記一次。

        用最長匹配掃過送出的內容，而不是重跑詞網格。送出時每一格通常都是 locked
        （使用者選過或詞彙鎖定過），而 locked 在詞網格裡是硬邊界——重跑只會得到
        一串單字，一個詞都記不到。這裡要的也不是「網格覺得該怎麼切」，而是「送出
        的這段文字由哪些已知的詞組成」。

        只記兩個字以上、而且詞庫或個人詞庫真的認得的跨度。認不得的就跳過一格，
        不要把隨機的字組當成詞餵進去。
        """
        if len(self.segments) < MIN_PHRASE_LENGTH:
            return
        readings = [segment.reading for segment in self.segments]
        text = "".join(segment.text for segment in self.segments)
        index = 0
        while index < len(readings):
            widest = min(MAX_PHRASE_LENGTH, len(readings) - index)
            for width in range(widest, MIN_PHRASE_LENGTH - 1, -1):
                span_readings = readings[index : index + width]
                span_text = text[index : index + width]
                if not all(
                    is_typable_reading(reading) for reading in span_readings
                ):
                    continue
                known = span_text in self.session.lexical_phrase_candidates(
                    span_readings
                ) or self.phrase_store.exact(span_readings) == span_text
                if known:
                    self.word_usage.record(span_readings, span_text)
                    index += width
                    break
            else:
                index += 1

    def _weighted_phrase(self, readings: list[str], phrase: str) -> int:
        """詞庫權重加上你自己用過幾次。

        內建權重是全語料的統計，這一項是你的。兩個都是「這個詞有多常見」，只是
        母體不同，所以直接相加而不是誰覆寫誰——用得夠多就贏得過詞庫，用得不多
        就只是往前挪一點。

        每次 WORD_USE_BONUS 的量級是照詞庫權重的尺度挑的：一步(5813) 對
        一部(21778) 差一萬六，用個八次就能翻過來。個人偏好該在「用了幾次」之後
        生效，不是第一次就搶走。
        """
        base = self.session.phrase_weight(readings, phrase)
        return base + self.word_usage.count(readings, phrase) * WORD_USE_BONUS

    def _personal_phrase(self, readings: list[str], context: str) -> tuple[str, bool]:
        """The user's word for these readings, and whether the context backs it.

        Context wins when it exists: 寫→程式 and 座→城市 are recorded
        separately, so one of them can no longer wreck the other's sentence.

        Falling back to the context-free memory keeps every phrase already in
        phrases.json working. It simply stops being able to overrule a far more
        common word without evidence that it belongs in this particular spot --
        the decoder decides that, see PERSONAL_OVERRIDE_RATIO.
        """
        remembered = self.context_store.lookup(readings, context)
        if remembered:
            return (remembered, True)
        return (self.phrase_store.exact(readings), False)

    def _learn_context(self, start: int, end: int, text: str) -> None:
        """Record what the user chose here, and what it followed.

        Only spans the user actually corrected reach this. Learning from the
        engine's own guesses would fill the store with the defaults it already
        produces, and then confirm them forever.
        """
        if start <= 0 or not MIN_PHRASE_LENGTH <= end - start <= MAX_PHRASE_LENGTH:
            return
        self.context_store.learn(
            [segment.reading for segment in self.segments[start:end]],
            text,
            self.segments[start - 1].text[-1],
        )

    def _typable_runs(self) -> list[tuple[int, int]]:
        """Maximal spans of segments whose readings are real Bopomofo.

        A literal ASCII segment inserted mid-composition -- ``我們=好`` -- has
        no reading libchewing can be asked about, and handing it one raised
        straight out of onKeyDown, taking the whole uncommitted composition
        with it. It is also a genuine phrase boundary: 我們=好 is not a word.

        Ranking each run on its own therefore fixes the crash and keeps the
        correction the user actually wants -- 我們 on the left still gets it,
        instead of the whole buffer silently losing phrase ranking as soon as
        one symbol appears anywhere in it.
        """
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for index, segment in enumerate(self.segments):
            if is_typable_reading(segment.reading):
                if start is None:
                    start = index
            elif start is not None:
                runs.append((start, index))
                start = None
        if start is not None:
            runs.append((start, len(self.segments)))
        return runs

    def _apply_phrase_ranking(self) -> None:
        """Decode every unlocked span, then apply whole-sentence correction."""
        if len(self.segments) < 2:
            return
        for start, end in self._typable_runs():
            if end - start < 2:
                continue
            self._apply_phrase_lattice(start, end)
            options = self._ranked_phrase_options(start, end)
            default = options[0] if options else ""
            if default:
                self._apply_ranked_phrase(end - start, default, end=end)

    def _apply_phrase_lattice(self, start: int = 0, end: int | None = None) -> None:
        """Compose one sentence from multiple exact-reading common words."""
        if end is None:
            end = len(self.segments)
        window = self.segments[start:end]
        readings = [segment.reading for segment in window]
        current_text = "".join(segment.text for segment in window)
        protected = [segment.locked for segment in window]
        spans = decode_phrase_lattice(
            readings,
            current_text,
            protected,
            self.session.lexical_phrase_candidates,
            self._weighted_phrase,
            self._personal_phrase,
            MAX_PHRASE_LENGTH,
        )
        for span in spans:
            # 「一律隱藏」的字不能從這裡溜進組字區。詞網格是直接把選中的字寫進
            # 去的，繞過候選字過濾——實測把「喫」加進隱藏名單完全沒有效果，因為
            # 擋的是候選清單，而畫面上的字根本不是從那裡來的。
            if any(HIDDEN_CHARACTERS.is_hidden(c) for c in span.text):
                continue
            # decode_phrase_lattice indexes the window it was given, so shift
            # back to buffer coordinates before writing.
            for segment, character in zip(
                self.segments[start + span.start : start + span.end], span.text
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
        self, width: int, phrase: str, lock: bool = False, end: int | None = None
    ) -> None:
        """Move one phrase to the front without replacing locked segments.

        ``end`` defaults to the end of the buffer, which is where every caller
        wanted it until literal ASCII started splitting the buffer into runs
        that do not reach it.
        """
        if end is None:
            end = len(self.segments)
        start = end - width
        if width < 1 or len(phrase) != width or start < 0 or end > len(self.segments):
            return
        if any(HIDDEN_CHARACTERS.is_hidden(character) for character in phrase):
            return
        for segment, suggested in zip(self.segments[start:end], phrase):
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
        # Draw the reading in progress where the caret is, not always at the
        # end. Honouring only Backspace's gap put a half-typed 我們|好ㄉ at the
        # far right, so the reading appeared to jump before it was even
        # finished. _accept_active_candidate resolves the final position the
        # same way, so what is drawn and where it lands agree.
        if self.replacement_index is not None:
            active_index = self.replacement_index
        elif self.focus_index is not None:
            active_index = self.focus_index + 1
        else:
            active_index = len(segment_texts)

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
        # A composition the user corrected by hand is the strongest personal
        # signal there is, yet it used to vanish at commit: only whole-choice
        # picks learned phrases, so a sentence assembled from per-character
        # fixes was forgotten and the next conversion repeated the old
        # default (first real-user report: a corrected 魔物獵人 re-typed as
        # 麼惡獵人). Engine-only output stays unlearned on purpose — commits
        # the user never touched must not reinforce themselves.
        if (
            len(self.segments) >= MIN_PHRASE_LENGTH
            and any(segment.user_corrected for segment in self.segments)
            and all(len(segment.text) == 1 for segment in self.segments)
        ):
            # Name the runs the user actually fixed. Learning every substring
            # instead turned one sentence into dozens of word-boundary
            # fragments; a real store reached 6912 entries that way. The
            # corrected runs are the parts worth recalling on their own.
            corrected_spans = []
            run_start = None
            for index, segment in enumerate(self.segments):
                if segment.user_corrected:
                    if run_start is None:
                        run_start = index
                elif run_start is not None:
                    corrected_spans.append((run_start, index))
                    run_start = None
            if run_start is not None:
                corrected_spans.append((run_start, len(self.segments)))

            self.phrase_store.learn(
                [segment.reading for segment in self.segments],
                text,
                extra_spans=corrected_spans,
            )
            # 同一批親手修正過的跨度，也記下它接在哪個字後面。學整句沒有意義：
            # 句首那一段沒有左鄰字，而整句本來就已經是 phrases.json 的職責。
            for span_start, span_end in corrected_spans:
                self._learn_context(
                    span_start, span_end, text[span_start:span_end]
                )
        self._record_word_usage()
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
