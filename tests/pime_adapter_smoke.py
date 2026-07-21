"""Smoke-test PIME's editable multi-character composition buffer.

Run with PIME's bundled 32-bit Python after building the overlay.  This file
is deliberately not named ``test_*.py`` because the normal test runner is
64-bit and cannot load PIME's 32-bit libchewing DLL.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIME_ROOT = Path(os.environ.get("PIME_ROOT", r"C:\Program Files (x86)\PIME"))
sys.path.insert(0, str(PIME_ROOT / "python"))
sys.path.insert(0, str(PROJECT_ROOT / "dist" / "PIME-overlay" / "python" / "input_methods"))

from pinned_bopomofo.pinned_bopomofo_ime import PinnedBopomofoTextService
from pinned_bopomofo.bopomofo_core.keymap import keys_for_reading
from pinned_bopomofo.bopomofo_core.state import INITIALS, MEDIALS, RIMES


class DummyClient:
    isWindows8Above = True


def key_message(character: str, sequence: int) -> dict:
    key_code = ord(character.upper())
    key_states = [0] * 256
    key_states[key_code] = 0x80
    return {
        "method": "onKeyDown",
        "seqNum": sequence,
        "charCode": ord(character),
        "keyCode": key_code,
        "repeatCount": 1,
        "scanCode": 0,
        "isExtended": False,
        "keyStates": key_states,
    }


def press(service, character: str, sequence: int) -> dict:
    reply = service.handleRequest(key_message(character, sequence))
    assert reply["success"]
    assert reply["return"] is True
    return reply


def special_key(service, key_code: int, sequence: int) -> dict:
    key_states = [0] * 256
    key_states[key_code] = 0x80
    reply = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence,
            "charCode": 0,
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": key_states,
        }
    )
    assert reply["success"]
    assert reply["return"] is True
    return reply


def candidate_selection_key(service, index: int, sequence: int) -> dict:
    if not 0 <= index <= 9:
        raise AssertionError(f"candidate index outside current page: {index}")
    key_code = 0x30 if index == 9 else 0x31 + index
    return special_key(service, key_code, sequence)


def shifted_key(service, key_code: int, sequence: int) -> dict:
    key_states = [0] * 256
    key_states[0x10] = 0x80  # VK_SHIFT
    key_states[key_code] = 0x80
    reply = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence,
            "charCode": 0,
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": key_states,
        }
    )
    assert reply["success"]
    assert reply["return"] is True
    return reply


def numpad_key(service, digit: int, sequence: int) -> dict:
    key_code = 0x60 + digit
    reply = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence,
            "charCode": ord(str(digit)),
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": [0] * 256,
        }
    )
    assert reply["success"]
    assert reply["return"] is True
    return reply


def numpad_decimal_key(service, sequence: int) -> dict:
    reply = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence,
            "charCode": 0,
            "keyCode": 0x6E,  # VK_DECIMAL
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": [0] * 256,
        }
    )
    assert reply["success"]
    assert reply["return"] is True
    return reply


def numpad_operator_key(service, key_code: int, sequence: int) -> dict:
    reply = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence,
            "charCode": 0,
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": key_code == 0x6F,
            "keyStates": [0] * 256,
        }
    )
    assert reply["success"]
    assert reply["return"] is True
    return reply


def filter_key(service, method: str, key_code: int, sequence: int, shift=False):
    key_states = [0] * 256
    if shift:
        key_states[0x10] = 0x80
    if method == "filterKeyDown":
        key_states[key_code] = 0x80
    return service.handleRequest(
        {
            "method": method,
            "seqNum": sequence,
            "charCode": 0,
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": key_states,
        }
    )


def tap_shift(service, sequence: int) -> tuple[int, dict]:
    filter_key(service, "filterKeyDown", 0x10, sequence, shift=True)
    filtered = filter_key(service, "filterKeyUp", 0x10, sequence + 1)
    assert filtered["return"] is True
    key_states = [0] * 256
    handled = service.handleRequest(
        {
            "method": "onKeyUp",
            "seqNum": sequence + 2,
            "charCode": 0,
            "keyCode": 0x10,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": key_states,
        }
    )
    assert handled["return"] is True
    return sequence + 3, handled


def hold_shift_letter(
    service, character: str, sequence: int
) -> tuple[int, dict]:
    """Press Shift+letter and release both without triggering mode toggle."""
    filter_key(service, "filterKeyDown", 0x10, sequence, shift=True)
    key_code = ord(character.upper())
    filtered = filter_key(
        service, "filterKeyDown", key_code, sequence + 1, shift=True
    )
    assert filtered["return"] is True

    key_states = [0] * 256
    key_states[0x10] = 0x80
    key_states[key_code] = 0x80
    handled = service.handleRequest(
        {
            "method": "onKeyDown",
            "seqNum": sequence + 2,
            "charCode": ord(character.upper()),
            "keyCode": key_code,
            "repeatCount": 1,
            "scanCode": 0,
            "isExtended": False,
            "keyStates": key_states,
        }
    )
    assert handled["return"] is True
    filter_key(service, "filterKeyUp", key_code, sequence + 3, shift=True)
    released = filter_key(service, "filterKeyUp", 0x10, sequence + 4)
    assert released["return"] is False
    return sequence + 5, handled


def type_readings(service, readings: list[str], sequence: int) -> int:
    for reading in readings:
        for key in keys_for_reading(reading):
            press(service, key, sequence)
            sequence += 1
    return sequence


def force_composition_text(service, text: str, *, locked: bool = True) -> None:
    """Put a known wrong homophone into completed segments for edit tests."""
    assert len(service.segments) == len(text)
    for segment, character in zip(service.segments, text):
        segment.candidates = list(
            dict.fromkeys([character] + segment.candidates)
        )
        segment.selected = 0
        segment.locked = locked
    service.focus_index = len(service.segments) - 1
    service._render_buffer()


def main() -> None:
    with tempfile.TemporaryDirectory() as appdata:
        os.environ["APPDATA"] = appdata
        service = PinnedBopomofoTextService(DummyClient())

        # Match Microsoft Bopomofo's vertical-first grid: 1-5 in the left
        # column, 6-0 in the right column, and no letter selectors.
        activation_reply = service.handleRequest(
            {"method": "onActivate", "seqNum": 0, "isKeyboardOpen": False}
        )
        assert activation_reply["setSelKeys"] == "1234567890"
        assert activation_reply["customizeUI"]["candPerRow"] == 2
        assert activation_reply["customizeUI"]["candFontSize"] == 16

        # ㄋㄧˇ -> 你 remains inside the composition instead of being sent
        # to the application immediately.
        press(service, "s", 1)
        press(service, "u", 2)
        press(service, "3", 3)
        assert service.provisional
        assert service.compositionString == "你"
        assert len(service.segments) == 1

        # The first key of ㄏㄠˇ arrives immediately.  No per-character commit
        # means TSF has no old-composition callback that can swallow ㄏ.
        boundary_reply = press(service, "c", 4)
        assert service.session.preedit == "ㄏ"
        assert service.compositionString == "你ㄏ"
        assert "commitString" not in boundary_reply

        # Finish ㄏㄠˇ -> 好.  Both characters remain under one composition.
        press(service, "l", 5)
        press(service, "3", 6)
        assert service.provisional
        assert service.compositionString == "你好"
        assert len(service.segments) == 2

        # Move to the previous character, open its candidate list, and use a
        # number key.  The number must select, never become a Bopomofo tone.
        special_key(service, 0x25, 7)  # VK_LEFT
        special_key(service, 0x25, 8)  # caret now sits before the first char
        assert service.focus_index == -1
        special_key(service, 0x28, 9)  # VK_DOWN
        assert service.showCandidates
        original_reading = service.segments[0].reading
        second_candidate = next(
            candidate
            for candidate in service.segments[0].candidates[1:]
            if not service._is_literal_bopomofo(candidate)
        )
        single_choice_index = next(
            index
            for index, choice in enumerate(service.candidate_choices)
            if choice.width == 1 and choice.text == second_candidate
        )
        for page_offset in range(single_choice_index // 10):
            special_key(service, 0x27, 10 + page_offset)
        candidate_selection_key(
            service, single_choice_index % 10, 10 + single_choice_index // 10
        )  # physical number, even when charCode is absent
        assert not service.showCandidates
        assert service.segments[0].selected == 0
        assert service.segments[0].candidates[0] == second_candidate
        assert service.segments[0].reading == original_reading
        assert service.compositionString == second_candidate + "好"
        assert service.session.preedit == ""
        assert service.focus_index == 0
        assert service._candidate_segment_index() == 1

        # Backspace on a completed character deletes it directly; it must not
        # turn back into a Bopomofo reading.
        special_key(service, 0x27, 11)  # VK_RIGHT, move caret to the end
        special_key(service, 0x08, 12)  # VK_BACK
        assert service.compositionString == second_candidate
        assert len(service.segments) == 1
        assert service.session.preedit == ""

        # Re-enter 好 so the whole-buffer commit is covered as well.
        # Deleting in the middle leaves a real insertion gap. The next
        # syllable must fill that position instead of jumping to the far end.
        insertion_service = PinnedBopomofoTextService(DummyClient())
        insertion_readings = ["ㄨㄣˊ", "ㄗˋ", "ㄘㄜˋ", "ㄕˋ"]
        insertion_sequence = type_readings(
            insertion_service, insertion_readings, 1000
        )
        special_key(insertion_service, 0x25, insertion_sequence)  # VK_LEFT
        special_key(insertion_service, 0x25, insertion_sequence + 1)
        special_key(insertion_service, 0x08, insertion_sequence + 2)  # VK_BACK
        type_readings(insertion_service, ["ㄋㄧˇ"], insertion_sequence + 3)
        actual_readings = [
            segment.reading for segment in insertion_service.segments
        ]
        assert actual_readings == ["ㄨㄣˊ", "ㄋㄧˇ", "ㄘㄜˋ", "ㄕˋ"]

        press(service, "c", 13)
        press(service, "l", 14)
        press(service, "3", 15)
        assert service.compositionString == second_candidate + "好"

        # Enter sends the entire edited composition in one commit.
        commit_reply = special_key(service, 0x0D, 16)  # VK_RETURN
        assert commit_reply["commitString"] == second_candidate + "好"
        assert service.compositionString == ""
        assert service.segments == []

        # Enter applies only high-confidence offline typo rules. The correction
        # happens before commit and never writes the surrounding sentence to a
        # store or network service.
        autocorrect_service = PinnedBopomofoTextService(DummyClient())
        autocorrect_sequence = type_readings(
            autocorrect_service,
            ["ㄨㄛˇ", "ㄧㄣˉ", "ㄍㄞˉ", "ㄅㄨˋ", "ㄏㄨㄟˋ", "ㄑㄩˋ"],
            1100,
        )
        force_composition_text(autocorrect_service, "我音該不會去", locked=False)
        autocorrect_reply = special_key(
            autocorrect_service, 0x0D, autocorrect_sequence
        )
        assert autocorrect_reply["commitString"] == "我應該不會去"

        # The same decoder also handles an exact ㄧㄥ reading without needing
        # a separate 英該 surface rule.
        exact_reading_service = PinnedBopomofoTextService(DummyClient())
        exact_reading_sequence = type_readings(
            exact_reading_service, ["ㄧㄥˉ", "ㄍㄞˉ"], 1150
        )
        force_composition_text(exact_reading_service, "英該", locked=False)
        exact_reading_reply = special_key(
            exact_reading_service, 0x0D, exact_reading_sequence
        )
        assert exact_reading_reply["commitString"] == "應該"

        # A real word using ㄧㄣ remains untouched; fuzzy ㄣ/ㄥ decoding must
        # not turn every occurrence of 音 into 應.
        valid_phrase_service = PinnedBopomofoTextService(DummyClient())
        valid_phrase_sequence = type_readings(
            valid_phrase_service, ["ㄧㄣˉ", "ㄍㄢˇ"], 1160
        )
        force_composition_text(valid_phrase_service, "音感", locked=False)
        valid_phrase_reply = special_key(
            valid_phrase_service, 0x0D, valid_phrase_sequence
        )
        assert valid_phrase_reply["commitString"] == "音感"

        # Exact-reading language-model corrections also update the live
        # composition instead of waiting for the candidate menu or Enter.
        for readings, wrong, expected, start_sequence in (
            (["ㄧㄡˉ", "ㄒㄧㄢˉ"], "優仙", "優先", 1170),
            (["ㄅㄨˋ", "ㄏㄜˊ", "ㄌㄧˇ"], "部合理", "不合理", 1180),
        ):
            live_service = PinnedBopomofoTextService(DummyClient())
            type_readings(live_service, readings, start_sequence)
            force_composition_text(live_service, wrong, locked=False)
            live_service._apply_phrase_ranking()
            live_service._render_buffer()
            assert live_service.compositionString == expected, (
                readings,
                wrong,
                live_service.compositionString,
            )

        # A character explicitly chosen by the user is protected. This is the
        # strongest priority and intentionally preserves a literal discussion
        # of a misspelling such as 因該.
        protected_service = PinnedBopomofoTextService(DummyClient())
        protected_sequence = type_readings(
            protected_service, ["ㄧㄣˉ", "ㄍㄞˉ"], 1120
        )
        force_composition_text(protected_service, "因該")
        protected_service.segments[0].locked = True
        protected_reply = special_key(
            protected_service, 0x0D, protected_sequence
        )
        assert protected_reply["commitString"] == "因該"

        personal_service = PinnedBopomofoTextService(DummyClient())
        personal_service.phrase_store.learn(["ㄧㄣˉ", "ㄍㄞˉ"], "因該")
        personal_sequence = type_readings(
            personal_service, ["ㄧㄣˉ", "ㄍㄞˉ"], 1130
        )
        assert personal_service.compositionString == "因該"
        assert all(segment.locked for segment in personal_service.segments)
        personal_reply = special_key(
            personal_service, 0x0D, personal_sequence
        )
        assert personal_reply["commitString"] == "因該"

        # The first release deliberately corrects only an explicit Enter
        # confirmation; ordinary Space preserves exactly what was composed.
        literal_service = PinnedBopomofoTextService(DummyClient())
        literal_sequence = type_readings(
            literal_service, ["ㄧㄣˉ", "ㄍㄞˉ"], 1140
        )
        force_composition_text(literal_service, "因該")
        literal_reply = press(literal_service, " ", literal_sequence)
        assert literal_reply["commitString"] == "因該 "

        # A candidate chosen with a number key is learned automatically and
        # becomes first for the same reading in a fresh service instance.
        learned_service = PinnedBopomofoTextService(DummyClient())
        press(learned_service, "s", 17)
        press(learned_service, "u", 18)
        press(learned_service, "3", 19)
        assert learned_service.segments[0].candidates[0] == second_candidate
        assert learned_service.compositionString == second_candidate

        # A real forced termination still clears everything.
        learned_service.english_mode = True
        terminated_reply = learned_service.handleRequest(
            {"method": "onCompositionTerminated", "seqNum": 20, "forced": True}
        )
        assert learned_service.session.preedit == ""
        assert learned_service.compositionString == ""
        assert not learned_service.provisional
        assert not learned_service.english_mode
        assert terminated_reply["openKeyboard"] is True

        # The full tsi.dat phrase index ranks common 2/3-character words while
        # the UI continues to hold independently editable character segments.
        phrase_examples = (
            (["ㄕㄨˋ", "ㄧㄝˋ"], "樹葉"),
            (["ㄗˋ", "ㄉㄧㄢˇ"], "字典"),
            (["ㄐㄧㄚˇ", "ㄕㄜˋ"], "假設"),
            (["ㄒㄧㄝˇ", "ㄔㄥˊ", "ㄕˋ"], "寫程式"),
            (["ㄉㄨㄟˋ", "ㄏㄨㄚˋ", "ㄎㄨㄤˉ"], "對話框"),
            (["ㄅㄨˋ", "ㄓˉ", "ㄉㄠˋ"], "不知道"),
            (["ㄍㄣˉ", "ㄗㄞˋ"], "跟在"),
            (["ㄗㄞˋ", "ㄐㄧㄚˉ"], "在家"),
            (["ㄗㄞˋ", "ㄧˉ", "ㄘˋ"], "再一次"),
        )
        sequence = 21
        for readings, expected in phrase_examples:
            phrase_service = PinnedBopomofoTextService(DummyClient())
            sequence = type_readings(phrase_service, readings, sequence)
            assert phrase_service.compositionString == expected, (
                readings,
                expected,
                phrase_service.compositionString,
            )
            assert len(phrase_service.segments) == len(expected)

        # CORE CONTRACT: phrase coverage is compared before source weight.
        # The shorter official word 畫框 must not overwrite libchewing's
        # correct three-syllable conversion 對話框.
        dialog_service = PinnedBopomofoTextService(DummyClient())
        dialog_readings = ["ㄉㄨㄟˋ", "ㄏㄨㄚˋ", "ㄎㄨㄤˉ"]
        sequence = type_readings(dialog_service, dialog_readings, sequence)
        shorter_matches = dialog_service.session.frequent_phrase_candidates(
            [segment.candidates for segment in dialog_service.segments[-2:]]
        )
        assert shorter_matches[0] == "畫框"
        assert dialog_service.session.best_phrase(dialog_readings) == "對話框"
        assert dialog_service.compositionString == "對話框"

        # The bundled Rime Essay derivative contributes over 100k offline
        # Taiwan-Traditional phrases and is filtered through exact-tone single
        # character candidates before it can affect the composition.
        expanded_service = PinnedBopomofoTextService(DummyClient())
        expanded_readings = ["ㄖㄣˊ", "ㄍㄨㄥˉ", "ㄓˋ", "ㄏㄨㄟˋ"]
        sequence = type_readings(expanded_service, expanded_readings, sequence)
        frequency_matches = expanded_service.session.frequent_phrase_candidates(
            [segment.candidates for segment in expanded_service.segments]
        )
        assert frequency_matches[0] == "人工智慧"
        assert expanded_service.compositionString == "人工智慧"

        # Automatic acceptance/commit must not reinforce itself. Only an
        # explicit candidate choice is allowed to enter the personal layer.
        automatic_service = PinnedBopomofoTextService(DummyClient())
        automatic_readings = ["ㄖㄨˊ", "ㄍㄨㄛˇ"]
        assert automatic_service.phrase_store.exact(automatic_readings) == ""
        sequence = type_readings(
            automatic_service, automatic_readings, sequence
        )
        special_key(automatic_service, 0x0D, sequence)
        sequence += 1
        assert automatic_service.phrase_store.exact(automatic_readings) == ""

        # CORE CONTRACT: candidate editing offers whole words, not only the
        # single character to the caret's right. Selecting a word replaces all
        # of its syllable segments together and records it as a personal word.
        optimize_service = PinnedBopomofoTextService(DummyClient())
        optimize_readings = ["ㄧㄡˉ", "ㄏㄨㄚˋ"]
        sequence = type_readings(optimize_service, optimize_readings, sequence)
        assert optimize_service.compositionString == "優化"
        force_composition_text(optimize_service, "優話")
        special_key(optimize_service, 0x28, sequence)  # VK_DOWN
        sequence += 1
        assert optimize_service.candidateList[0] == "優化"
        assert optimize_service.candidate_choices[0].width == 2
        special_key(optimize_service, 0x31, sequence)  # choose whole word
        sequence += 1
        assert optimize_service.compositionString == "優化"
        assert [segment.text for segment in optimize_service.segments] == list("優化")
        feedback = optimize_service.feedback_store.entries()
        assert any(
            entry["converted"] == "優話" and entry["expected"] == "優化"
            for entry in feedback
        )

        # Protected defaults distinguish an isolated character from a word:
        # ㄗˋ starts as 字, then contextual phrase ranking may form 自己/自我.
        zi_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(zi_service, ["ㄗˋ"], sequence)
        assert zi_service.compositionString == "字"
        na_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(na_service, ["ㄋㄚˋ"], sequence)
        assert na_service.compositionString == "那"
        self_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(self_service, ["ㄗˋ", "ㄐㄧˇ"], sequence)
        assert self_service.compositionString == "自己"

        # Once a high-confidence word is resolved, later syllables cannot
        # reach backwards and alter it. The protected 優先級 spelling also
        # beats the homophonous 優先及.
        stable_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(stable_service, optimize_readings, sequence)
        assert stable_service.compositionString == "優化"
        sequence = type_readings(
            stable_service, ["ㄧˊ", "ㄒㄧㄚˋ"], sequence
        )
        assert stable_service.compositionString == "優化一下"

        priority_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(
            priority_service,
            ["ㄧㄡˉ", "ㄒㄧㄢˉ", "ㄐㄧˊ"],
            sequence,
        )
        assert priority_service.compositionString == "優先級"

        # Explicit personal learning is stronger than every bundled default,
        # even when the selected phrase is unusual.
        personal_priority = PinnedBopomofoTextService(DummyClient())
        personal_priority.phrase_store.learn(optimize_readings, "優話")
        sequence = type_readings(personal_priority, optimize_readings, sequence)
        assert personal_priority.compositionString == "優話"

        # A new explicit single-character correction replaces the previous
        # personal priority for that reading. In particular, selecting 字 after
        # an old 自 preference must persist and win in the next service.
        relearn_service = PinnedBopomofoTextService(DummyClient())
        relearn_service.session.pins.pin("ㄗˋ", "自")
        sequence = type_readings(relearn_service, ["ㄗˋ"], sequence)
        assert relearn_service.compositionString == "自"
        special_key(relearn_service, 0x28, sequence)  # candidate menu
        sequence += 1
        zi_choice = next(
            index
            for index, choice in enumerate(relearn_service.candidate_choices)
            if choice.width == 1 and choice.text == "字"
        )
        for _ in range(zi_choice // 10):
            special_key(relearn_service, 0x27, sequence)  # next page
            sequence += 1
        candidate_selection_key(relearn_service, zi_choice % 10, sequence)
        sequence += 1
        assert relearn_service.session.pins.phrases_for("ㄗˋ")[0] == "字"
        relearned_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(relearned_service, ["ㄗˋ"], sequence)
        assert relearned_service.compositionString == "字"

        program_service = PinnedBopomofoTextService(DummyClient())
        program_readings = ["ㄒㄧㄝˇ", "ㄔㄥˊ", "ㄕˋ"]
        sequence = type_readings(program_service, program_readings, sequence)
        force_composition_text(program_service, "寫城市")
        special_key(program_service, 0x28, sequence)
        sequence += 1
        assert program_service.candidateList[0] == "寫程式"
        assert program_service.candidate_choices[0].width == 3
        special_key(program_service, 0x31, sequence)
        sequence += 1
        assert program_service.compositionString == "寫程式"

        four_word_service = PinnedBopomofoTextService(DummyClient())
        four_readings = ["ㄧˊ", "ㄆㄧㄢˋ", "ㄕㄨˋ", "ㄧㄝˋ"]
        four_word_service.phrase_store.learn(four_readings, "一片樹葉")
        sequence = type_readings(four_word_service, four_readings, sequence)
        force_composition_text(four_word_service, "姨騙數夜")
        special_key(four_word_service, 0x28, sequence)
        sequence += 1
        assert four_word_service.candidateList[0] == "一片樹葉"
        assert four_word_service.candidate_choices[0].width == 4
        special_key(four_word_service, 0x31, sequence)
        sequence += 1
        assert four_word_service.compositionString == "一片樹葉"

        # Personal phrases extend the built-in index and take precedence on
        # the next service instance.
        custom_readings = ["ㄕㄨˋ", "ㄧㄝˋ"]
        phrase_service.phrase_store.learn(custom_readings, "術業")
        personal_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(personal_service, custom_readings, sequence)
        assert personal_service.compositionString == "術業"

        # Shift+/ (the ㄥ key) emits a full-width question mark and commits an
        # existing composition with the punctuation attached.
        punctuation_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(
            punctuation_service, ["ㄗˋ", "ㄉㄧㄢˇ"], sequence
        )
        punctuation_reply = shifted_key(punctuation_service, 0xBF, sequence)
        sequence += 1
        assert punctuation_reply["commitString"] == "字典？"
        assert punctuation_service.compositionString == ""

        # Shift+quote alternates Taiwanese corner quotes.
        open_quote = shifted_key(punctuation_service, 0xDE, sequence)
        sequence += 1
        close_quote = shifted_key(punctuation_service, 0xDE, sequence)
        assert open_quote["commitString"] == "「"
        assert close_quote["commitString"] == "」"

        # A short standalone Shift press toggles Chinese/English.  Printable
        # keys pass through untouched in English mode, and Shift toggles back.
        mode_service = PinnedBopomofoTextService(DummyClient())
        activation_reply = mode_service.handleRequest(
            {
                "method": "onActivate",
                "seqNum": sequence,
                "isKeyboardOpen": False,
            }
        )
        sequence += 1
        assert activation_reply["openKeyboard"] is True
        assert mode_service.keyboardOpen
        assert not mode_service.english_mode
        sequence, _ = tap_shift(mode_service, sequence + 1)
        assert mode_service.english_mode
        english_a = key_message("a", sequence)
        english_a["method"] = "filterKeyDown"
        english_reply = mode_service.handleRequest(english_a)
        assert english_reply["return"] is False
        key_up_a = key_message("a", sequence + 1)
        key_up_a["method"] = "filterKeyUp"
        mode_service.handleRequest(key_up_a)
        sequence, _ = tap_shift(mode_service, sequence + 2)
        assert not mode_service.english_mode

        # Windows can close the keyboard compartment when focus changes.
        # This profile reopens it and resets its field-local English toggle.
        mode_service.english_mode = True
        status_reply = mode_service.handleRequest(
            {
                "method": "onKeyboardStatusChanged",
                "seqNum": sequence,
                "opened": False,
            }
        )
        sequence += 1
        assert status_reply["openKeyboard"] is True
        assert mode_service.keyboardOpen
        assert not mode_service.english_mode

        # CORE CONTRACT: holding Shift while pressing A-Z emits a temporary
        # uppercase English letter and stays in Chinese mode.  This behavior
        # is distinct from tapping Shift to toggle the persistent mode.
        temporary_service = PinnedBopomofoTextService(DummyClient())
        sequence, temporary_reply = hold_shift_letter(
            temporary_service, "a", sequence + 1
        )
        assert temporary_reply["commitString"] == "A"
        assert not temporary_service.english_mode

        # Pending Chinese must be committed before the temporary English
        # letter so applications can never place that letter at the left edge.
        ordering_service = PinnedBopomofoTextService(DummyClient())
        press(ordering_service, "s", sequence)  # ㄋ
        press(ordering_service, "u", sequence + 1)  # ㄧ
        press(ordering_service, "3", sequence + 2)  # ˇ -> 你
        expected_chinese = ordering_service.compositionString
        sequence, temporary_reply = hold_shift_letter(
            ordering_service, "b", sequence + 3
        )
        assert temporary_reply["commitString"] == expected_chinese + "B"
        assert temporary_reply["compositionString"] == ""
        assert not ordering_service.english_mode

        # An unfinished syllable is cancelled before the temporary letter;
        # any completed Chinese to its left is still committed in order.
        partial_temporary_service = PinnedBopomofoTextService(DummyClient())
        press(partial_temporary_service, "s", sequence)  # unfinished ㄋ
        sequence, temporary_reply = hold_shift_letter(
            partial_temporary_service, "c", sequence + 1
        )
        assert temporary_reply["commitString"] == "C"
        assert temporary_reply["compositionString"] == ""
        assert partial_temporary_service.session.preedit == ""
        assert not partial_temporary_service.english_mode

        # Shift punctuation follows the same replacement rule as Shift+A-Z.
        partial_symbol_service = PinnedBopomofoTextService(DummyClient())
        press(partial_symbol_service, "a", sequence)  # incomplete ㄇ
        symbol_reply = shifted_key(partial_symbol_service, 0xBF, sequence + 1)
        sequence += 2
        assert symbol_reply["commitString"] == "？"
        assert partial_symbol_service.session.preedit == ""

        # Numpad is always numeric text in Chinese mode. It cannot produce a
        # Bopomofo symbol or select candidate 1, and replaces a partial sound.
        numpad_service = PinnedBopomofoTextService(DummyClient())
        press(numpad_service, "a", sequence)  # incomplete ㄇ
        numpad_reply = numpad_key(numpad_service, 7, sequence + 1)
        sequence += 2
        assert numpad_reply["commitString"] == "7"
        assert numpad_service.session.preedit == ""

        numpad_composition = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(numpad_composition, ["ㄗˋ"], sequence)
        special_key(numpad_composition, 0x28, sequence)  # candidate menu
        numpad_reply = numpad_key(numpad_composition, 1, sequence + 1)
        sequence += 2
        assert numpad_reply["commitString"] == "字1"

        # CORE CONTRACT: the physical NumPad decimal key is direct text just
        # like NumPad 0-9. It must never fall through to the Bopomofo keymap,
        # even when charCode is absent or a candidate menu is open.
        decimal_service = PinnedBopomofoTextService(DummyClient())
        decimal_reply = numpad_decimal_key(decimal_service, sequence)
        sequence += 1
        assert decimal_reply["commitString"] == "."

        partial_decimal_service = PinnedBopomofoTextService(DummyClient())
        press(partial_decimal_service, "a", sequence)  # incomplete ㄇ
        decimal_reply = numpad_decimal_key(
            partial_decimal_service, sequence + 1
        )
        sequence += 2
        assert decimal_reply["commitString"] == "."
        assert partial_decimal_service.session.preedit == ""

        decimal_composition = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(decimal_composition, ["ㄗˋ"], sequence)
        special_key(decimal_composition, 0x28, sequence)  # candidate menu
        decimal_reply = numpad_decimal_key(decimal_composition, sequence + 1)
        sequence += 2
        assert decimal_reply["commitString"] == "字."
        assert not decimal_composition.showCandidates

        # Every visible numpad operator is literal text, never a DaQian
        # Bopomofo key. Check physical key codes with charCode absent.
        for key_code, expected in (
            (0x6F, "/"),  # VK_DIVIDE
            (0x6A, "*"),  # VK_MULTIPLY
            (0x6D, "-"),  # VK_SUBTRACT
            (0x6B, "+"),  # VK_ADD
        ):
            operator_service = PinnedBopomofoTextService(DummyClient())
            press(operator_service, "a", sequence)  # incomplete ㄇ
            operator_reply = numpad_operator_key(
                operator_service, key_code, sequence + 1
            )
            sequence += 2
            assert operator_reply["commitString"] == expected
            assert operator_service.session.preedit == ""

        insertion_direct = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(
            insertion_direct, ["ㄨㄣˊ", "ㄗˋ"], sequence
        )
        special_key(insertion_direct, 0x08, sequence)  # remove 字, leave gap
        press(insertion_direct, "a", sequence + 1)  # incomplete ㄇ at gap
        sequence, direct_reply = hold_shift_letter(
            insertion_direct, "d", sequence + 2
        )
        assert direct_reply["commitString"] == "文D"

        # As in Microsoft Bopomofo, a complete reading exposes the literal
        # Zhuyin spelling near the front without replacing normal Chinese.
        for reading, expected_literal in (
            ("ㄢˉ", "ㄢ"),
            ("ㄢˊ", "ㄢˊ"),
            ("ㄢˇ", "ㄢˇ"),
            ("ㄢˋ", "ㄢˋ"),
            ("ㄢ˙", "ㄢ˙"),
        ):
            tone_service = PinnedBopomofoTextService(DummyClient())
            sequence = type_readings(tone_service, [reading], sequence)
            if not tone_service.showCandidates:
                special_key(tone_service, 0x28, sequence)
                sequence += 1
            available_literals = (
                [choice.text for choice in tone_service.candidate_choices]
                if tone_service.candidate_choices
                else list(tone_service.session.candidates)
            )
            tone_choice = next(
                index
                for index, candidate in enumerate(available_literals)
                if candidate == expected_literal
            )
            assert tone_choice < 5
            literal_reply = candidate_selection_key(
                tone_service, tone_choice, sequence
            )
            sequence += 1
            assert literal_reply.get("commitString") == expected_literal, (
                reading,
                expected_literal,
                literal_reply,
            )
            assert tone_service.compositionString == ""

        # Space supplies first tone and the dictionary decides whether a lone
        # symbol can form Chinese. ㄉ cannot, while ㄜ and the syllabic initial
        # ㄙ can; raw Zhuyin remains available as an alternate.
        initial_literal = PinnedBopomofoTextService(DummyClient())
        press(initial_literal, "2", sequence)  # ㄉ
        initial_menu = press(initial_literal, " ", sequence + 1)
        assert initial_menu["candidateList"] == ["ㄉ"], initial_menu
        initial_reply = candidate_selection_key(initial_literal, 0, sequence + 2)
        assert initial_reply["commitString"] == "ㄉ"

        rime_literal = PinnedBopomofoTextService(DummyClient())
        press(rime_literal, "k", sequence + 3)  # ㄜ
        press(rime_literal, " ", sequence + 4)
        assert rime_literal.segments
        assert rime_literal.compositionString != "ㄜ"
        special_key(rime_literal, 0x28, sequence + 5)
        assert "ㄜ" in [choice.text for choice in rime_literal.candidate_choices[:4]]

        syllabic_initial = PinnedBopomofoTextService(DummyClient())
        syllabic_candidates = syllabic_initial.session.provider.candidates("ㄙˉ")
        press(syllabic_initial, keys_for_reading("ㄙ"), sequence + 6)
        press(syllabic_initial, " ", sequence + 7)
        assert syllabic_initial.compositionString == syllabic_candidates[0]
        assert not syllabic_initial.showCandidates

        # The reported real-world sequence must flow without opening a raw
        # Zhuyin menu: ㄧˋ + ㄙ + Space => 意思. Candidate zero and the text
        # actually inserted into the composition must always agree.
        meaning_service = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(meaning_service, ["ㄧˋ"], sequence + 8)
        press(meaning_service, keys_for_reading("ㄙ"), sequence)
        press(meaning_service, " ", sequence + 1)
        assert meaning_service.compositionString == "意思"
        assert not meaning_service.showCandidates
        assert all(
            segment.text == segment.candidates[0]
            for segment in meaning_service.segments
        )

        # Stored single-character preferences rank isolated input but cannot
        # freeze a bad character inside strong sentence context. This mirrors
        # a profile contaminated by older builds that learned 仙 and 不.
        contextual_readings = [
            "ㄋㄧˇ",
            "ㄒㄧㄢˉ",
            "ㄎㄞˉ",
            "ㄕˇ",
            "ㄒㄧㄚˋ",
            "ㄧˉ",
            "ㄅㄨˋ",
            "ㄅㄚ˙",
        ]
        contextual_service = PinnedBopomofoTextService(DummyClient())
        contextual_service.session.pins.pin("ㄒㄧㄢˉ", "仙")
        contextual_service.session.pins.pin("ㄅㄨˋ", "不")
        sequence = type_readings(
            contextual_service, contextual_readings, sequence + 2
        )
        assert contextual_service.compositionString == "你先開始下一步吧"
        assert not any(segment.locked for segment in contextual_service.segments)

        # The candidate editor may keep one whole-sentence correction, but it
        # must not expose unverified intermediate engine guesses such as
        # 你先開始夏衣 or 你掀開 ahead of useful words and characters.
        force_composition_text(
            contextual_service, "你仙開始下一不吧", locked=False
        )
        contextual_service.focus_index = -1
        choices = contextual_service._build_candidate_choices()
        choice_texts = [choice.text for choice in choices]
        assert choice_texts[0] == "你先開始下一步吧", choice_texts
        assert "你先開始夏衣" not in choice_texts
        assert "你掀開" not in choice_texts
        assert "你先" in choice_texts[:4], choice_texts

        # The actual Down-key path first applies that shared default. The
        # correct sentence must already be visible in the editable buffer,
        # rather than existing only as candidate number one.
        special_key(contextual_service, 0x28, sequence)
        sequence += 1
        assert contextual_service.compositionString == "你先開始下一步吧"
        assert "你先開始夏衣" not in contextual_service.candidateList
        assert "你掀開" not in contextual_service.candidateList

        # Every commit path synchronizes the same default even if an unlocked
        # stale buffer somehow survived from an older build or edit action.
        enter_default = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(enter_default, contextual_readings, sequence)
        force_composition_text(enter_default, "你仙開始下一不吧", locked=False)
        enter_reply = special_key(enter_default, 0x0D, sequence)
        sequence += 1
        assert enter_reply["commitString"] == "你先開始下一步吧"

        space_default = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(space_default, contextual_readings, sequence)
        force_composition_text(space_default, "你仙開始下一不吧", locked=False)
        space_reply = press(space_default, " ", sequence)
        sequence += 1
        assert space_reply["commitString"] == "你先開始下一步吧 "

        # Opening the editor at the end of a sentence must not waste the
        # highest-ranked slots on no-op copies of the current sentence and
        # each of its shorter suffix spans.
        no_op_service = PinnedBopomofoTextService(DummyClient())
        no_op_readings = ["ㄨㄛˇ", "ㄧㄥˉ", "ㄍㄞˉ", "ㄅㄨˋ", "ㄏㄨㄟˋ", "ㄑㄩˋ"]
        sequence = type_readings(no_op_service, no_op_readings, sequence)
        special_key(no_op_service, 0x28, sequence)
        for choice in no_op_service.candidate_choices:
            if choice.width == 1:
                continue
            occupied = "".join(
                segment.text for segment in no_op_service.segments[choice.start : choice.end]
            )
            assert choice.text != occupied, (
                choice,
                no_op_service.compositionString,
            )

        standalone_tone = PinnedBopomofoTextService(DummyClient())
        tone_reply = press(standalone_tone, "3", sequence + 1)
        assert tone_reply["commitString"] == "ˇ"
        sequence += 2

        # Apply the dictionary-driven rule to every initial, medial, and rime,
        # not only examples reported by the user. Valid standalone forms must
        # select candidate zero and retain raw Zhuyin on page one; invalid
        # forms fall back to the literal safely.
        standalone_defaults = {}
        for literal in sorted(INITIALS | MEDIALS | RIMES):
            literal_service = PinnedBopomofoTextService(DummyClient())
            key = keys_for_reading(literal)
            assert len(key) == 1, (literal, key)
            candidates = literal_service.session.provider.candidates(literal + "ˉ")
            chinese = [
                candidate
                for candidate in candidates
                if len(candidate) == 1 and not literal_service._is_literal_bopomofo(candidate)
            ]
            chinese_first = bool(candidates) and not literal_service._is_literal_bopomofo(
                candidates[0]
            )
            press(literal_service, key, sequence)
            reply = press(literal_service, " ", sequence + 1)
            if chinese_first:
                assert literal_service.segments, (literal, reply)
                assert literal_service.compositionString == candidates[0], (
                    literal,
                    candidates,
                    literal_service.compositionString,
                )
                assert literal_service.segments[0].text == (
                    literal_service.segments[0].candidates[0]
                )
                standalone_defaults[literal] = chinese
                special_key(literal_service, 0x28, sequence + 2)
                choices = [choice.text for choice in literal_service.candidate_choices]
                assert literal in choices[:4], (literal, choices)
            else:
                assert reply["candidateList"][0] == literal, (literal, reply)
            sequence += 3
        assert standalone_defaults["ㄧ"][0] == "一"
        assert "阿" in standalone_defaults["ㄚ"]

        # Literal Zhuyin also remains on page one when editing a whole
        # uncommitted sentence containing phrase candidates.
        sentence_literal = PinnedBopomofoTextService(DummyClient())
        sequence = type_readings(
            sentence_literal, ["ㄉㄨㄟˋ", "ㄏㄨㄚˋ", "ㄎㄨㄤˉ"], sequence
        )
        special_key(sentence_literal, 0x28, sequence)
        sequence += 1
        assert "ㄎㄨㄤ" in sentence_literal.candidateList, (
            sentence_literal.candidateList
        )

        # Shift also switches when an unfinished Bopomofo reading is present;
        # the partial reading is cancelled instead of blocking mode changes.
        partial_service = PinnedBopomofoTextService(DummyClient())
        press(partial_service, "a", sequence)  # ㄇ, not a complete syllable
        assert partial_service.session.preedit == "ㄇ"
        sequence, _ = tap_shift(partial_service, sequence + 1)
        assert partial_service.english_mode
        assert partial_service.session.preedit == ""
        assert partial_service.compositionString == ""

        # Completed Chinese text is committed inside onKeyUp before English
        # input is allowed through, so English cannot jump in front of it.
        toggle_ordering_service = PinnedBopomofoTextService(DummyClient())
        press(toggle_ordering_service, "s", sequence)  # ㄋ
        press(toggle_ordering_service, "u", sequence + 1)  # ㄧ
        press(toggle_ordering_service, "3", sequence + 2)  # ˇ -> 你
        expected_chinese = toggle_ordering_service.compositionString
        sequence, toggle_reply = tap_shift(
            toggle_ordering_service, sequence + 3
        )
        assert toggle_reply["commitString"] == expected_chinese
        assert toggle_reply["compositionString"] == ""
        assert toggle_ordering_service.english_mode

        # The first page contains ten candidates in two vertical-first columns.
        # Right opens the next page, while Down walks 1-5 then 6-0 and flips.
        expanded_service = PinnedBopomofoTextService(DummyClient())
        press(expanded_service, "g", sequence)  # ㄕ
        press(expanded_service, "4", sequence + 1)  # ˋ
        assert len(expanded_service.segments[0].candidates) > 10
        open_reply = special_key(
            expanded_service, 0x28, sequence + 2
        )  # open first page
        assert open_reply["showCandidates"] is True
        assert len(expanded_service.candidateList) == 10
        first_page = list(expanded_service.candidateList)
        next_page_reply = special_key(
            expanded_service, 0x27, sequence + 3
        )
        assert next_page_reply["showCandidates"] is True
        assert expanded_service.candidate_page == 1
        assert expanded_service.candidateList
        assert expanded_service.candidateList != first_page
        assert expanded_service.candidateCursor == 0
        special_key(expanded_service, 0x25, sequence + 4)  # Left = prior page
        assert expanded_service.candidate_page == 0

        down_page_service = PinnedBopomofoTextService(DummyClient())
        press(down_page_service, "g", sequence + 5)
        press(down_page_service, "4", sequence + 6)
        special_key(down_page_service, 0x28, sequence + 7)
        for offset in range(10):
            special_key(down_page_service, 0x28, sequence + 8 + offset)
        assert down_page_service.candidate_page == 1
        assert down_page_service.candidateCursor == 0

        # Key 5 chooses the bottom of the left column and key 6 chooses the top
        # of the right column. Letters are not candidate selectors.
        fifth_service = PinnedBopomofoTextService(DummyClient())
        press(fifth_service, "g", sequence + 13)
        press(fifth_service, "4", sequence + 14)
        special_key(fifth_service, 0x28, sequence + 15)
        fifth_choice = fifth_service.candidate_choices[4]
        candidate_selection_key(fifth_service, 4, sequence + 16)
        assert fifth_service.compositionString == fifth_choice.text

        sixth_service = PinnedBopomofoTextService(DummyClient())
        press(sixth_service, "g", sequence + 17)
        press(sixth_service, "4", sequence + 18)
        special_key(sixth_service, 0x28, sequence + 19)
        sixth_choice = sixth_service.candidate_choices[5]
        candidate_selection_key(sixth_service, 5, sequence + 20)
        assert sixth_service.compositionString == sixth_choice.text
        sequence += 21

        # Invalid phonetics make only the configured gentle sound; the old
        # yellow showMessage tooltip must not be present in the PIME reply.
        phrase_service.currentReply = {}
        phrase_service._bell("這個音節沒有有效候選")
        assert "showMessage" not in phrase_service.currentReply

    print("PASS: editable buffer, phrase index, learning, and quiet errors")


if __name__ == "__main__":
    main()
