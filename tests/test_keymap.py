import unittest

from bopomofo_core.keymap import keys_for_reading, symbol_for_event, symbol_for_key


class DaQianKeymapTests(unittest.TestCase):
    def test_user_examples_use_standard_keys(self) -> None:
        self.assertEqual("ㄒㄩㄝˋ", "".join(symbol_for_key(key) for key in "vm,4"))
        self.assertEqual("ㄒㄧㄣˋ", "".join(symbol_for_key(key) for key in "vup4"))

    def test_initial_replacement_key(self) -> None:
        self.assertEqual("ㄑ", symbol_for_key("f"))

    def test_reading_can_be_replayed_into_libchewing(self) -> None:
        self.assertEqual("vm,4", keys_for_reading("ㄒㄩㄝˋ"))

    def test_physical_key_survives_missing_char_code(self) -> None:
        self.assertEqual("ㄩ", symbol_for_event(0x4D, 0))
        self.assertEqual("ㄢ", symbol_for_event(0x30, 0))
        self.assertEqual("ㄝ", symbol_for_event(0xBC, 0))


if __name__ == "__main__":
    unittest.main()
