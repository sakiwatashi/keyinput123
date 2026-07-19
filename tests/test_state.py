import unittest

from bopomofo_core.state import BopomofoEditor, EventKind


class BopomofoEditorTests(unittest.TestCase):
    def test_same_slot_replaces_after_tone(self) -> None:
        editor = BopomofoEditor()
        for symbol in "ㄒㄩㄝˋ":
            editor.input_symbol(symbol)
        event = editor.input_symbol("ㄑ")
        self.assertEqual(EventKind.UPDATED, event.kind)
        self.assertEqual("ㄑㄩㄝˋ", editor.preedit)

    def test_free_order_is_canonicalized(self) -> None:
        editor = BopomofoEditor()
        for symbol in "ㄧㄒㄣˋ":
            editor.input_symbol(symbol)
        self.assertEqual("ㄒㄧㄣˋ", editor.preedit)

    def test_tone_replacement_does_not_create_second_syllable(self) -> None:
        editor = BopomofoEditor()
        for symbol in "ㄒㄧㄣˋˇ":
            editor.input_symbol(symbol)
        self.assertEqual("ㄒㄧㄣˇ", editor.preedit)

    def test_commit_is_explicit_and_clears_editor(self) -> None:
        editor = BopomofoEditor()
        for symbol in "ㄒㄧㄣˋ":
            editor.input_symbol(symbol)
        event = editor.commit("信")
        self.assertEqual(EventKind.COMMITTED, event.kind)
        self.assertEqual("信", event.committed)
        self.assertTrue(editor.is_empty)

    def test_invalid_symbol_bells_without_mutation(self) -> None:
        editor = BopomofoEditor()
        editor.input_symbol("ㄒ")
        event = editor.input_symbol("A")
        self.assertEqual(EventKind.BELL, event.kind)
        self.assertEqual("ㄒ", editor.preedit)

    def test_candidate_validator_bells_without_mutation(self) -> None:
        editor = BopomofoEditor(validator=lambda reading: reading != "ㄐㄨ")
        editor.input_symbol("ㄐ")
        event = editor.input_symbol("ㄨ")
        self.assertEqual(EventKind.BELL, event.kind)
        self.assertEqual("ㄐ", editor.preedit)

    def test_backspace_removes_most_recently_edited_slot(self) -> None:
        editor = BopomofoEditor()
        for symbol in "ㄒㄩㄝˋㄑ":
            editor.input_symbol(symbol)
        editor.backspace()
        self.assertEqual("ㄩㄝˋ", editor.preedit)


if __name__ == "__main__":
    unittest.main()
