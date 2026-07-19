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


def force_composition_text(service, text: str) -> None:
    """Put a known wrong homophone into completed segments for edit tests."""
    assert len(service.segments) == len(text)
    for segment, character in zip(service.segments, text):
        segment.candidates = list(
            dict.fromkeys([character] + segment.candidates)
        )
        segment.selected = 0
        segment.locked = True
    service.focus_index = len(service.segments) - 1
    service._render_buffer()


def main() -> None:
    with tempfile.TemporaryDirectory() as appdata:
        os.environ["APPDATA"] = appdata
        service = PinnedBopomofoTextService(DummyClient())

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
        second_candidate = service.segments[0].candidates[1]
        single_choice_index = next(
            index
            for index, choice in enumerate(service.candidate_choices)
            if choice.width == 1 and choice.text == second_candidate
        )
        assert single_choice_index < 5
        special_key(
            service, 0x31 + single_choice_index, 10
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

        # The candidate menu starts compact.  Moving down past candidate five
        # expands the practical (top-20) list instead of wrapping around.
        expanded_service = PinnedBopomofoTextService(DummyClient())
        press(expanded_service, "g", sequence)  # ㄕ
        press(expanded_service, "4", sequence + 1)  # ˋ
        assert len(expanded_service.segments[0].candidates) > 5
        open_reply = special_key(
            expanded_service, 0x28, sequence + 2
        )  # open compact list
        assert open_reply["showCandidates"] is True
        assert len(expanded_service.candidateList) == 5
        for offset in range(3, 7):
            navigation_reply = special_key(
                expanded_service, 0x28, sequence + offset
            )
            assert navigation_reply["showCandidates"] is True
        assert expanded_service.candidateCursor == 4
        expansion_reply = special_key(
            expanded_service, 0x28, sequence + 7
        )
        assert expansion_reply["showCandidates"] is True
        assert expanded_service.candidate_expanded
        assert len(expanded_service.candidateList) > 5
        assert expanded_service.candidateCursor == 5

        # Invalid phonetics make only the configured gentle sound; the old
        # yellow showMessage tooltip must not be present in the PIME reply.
        phrase_service.currentReply = {}
        phrase_service._bell("這個音節沒有有效候選")
        assert "showMessage" not in phrase_service.currentReply

    print("PASS: editable buffer, phrase index, learning, and quiet errors")


if __name__ == "__main__":
    main()
