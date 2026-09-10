import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core import keymap


class LayoutValidationTests(unittest.TestCase):
    def test_a_complete_remap_is_accepted(self) -> None:
        swapped = dict(keymap.KEY_TO_SYMBOL)
        swapped["1"], swapped["q"] = swapped["q"], swapped["1"]

        layout, problem = keymap.validate_layout(swapped)

        self.assertEqual("", problem)
        self.assertEqual("ㄆ", layout["1"])
        self.assertEqual("ㄅ", layout["q"])

    def test_a_layout_that_cannot_type_every_sound_is_refused(self) -> None:
        # 少一個符號的配置會讓輸入法整天都正常，然後在某個讀音上完全打不出來。
        # 使用者沒有辦法把那件事連回一週前改過的檔案，所以這裡直接拒絕。
        incomplete = dict(keymap.KEY_TO_SYMBOL)
        del incomplete["1"]

        layout, problem = keymap.validate_layout(incomplete)

        self.assertIsNone(layout)
        self.assertIn("ㄅ", problem)

    def test_an_unknown_symbol_is_refused(self) -> None:
        broken = dict(keymap.KEY_TO_SYMBOL)
        broken["1"] = "A"
        layout, problem = keymap.validate_layout(broken)
        self.assertIsNone(layout)
        self.assertIn("不認得", problem)

    def test_a_multi_character_key_is_refused(self) -> None:
        broken = dict(keymap.KEY_TO_SYMBOL)
        broken["ctrl+1"] = "ㄅ"
        layout, problem = keymap.validate_layout(broken)
        self.assertIsNone(layout)
        self.assertIn("單一字元", problem)

    def test_rubbish_is_refused_rather_than_crashing(self) -> None:
        for value in ({}, [], "ㄅ", 42, None):
            layout, problem = keymap.validate_layout(value)
            self.assertIsNone(layout, f"{value!r} 不該被接受")
            self.assertTrue(problem)


class LayoutLoadingTests(unittest.TestCase):
    def tearDown(self) -> None:
        # 這些測試會換掉行程層級的作用中配置，不還原會污染後面的測試。
        keymap.load_layout(Path("this-file-does-not-exist.json"))

    def test_a_missing_file_leaves_the_built_in_layout_alone(self) -> None:
        problem = keymap.load_layout(Path("no-such-layout.json"))
        self.assertEqual("", problem)
        self.assertEqual("ㄅ", keymap.symbol_for_key("1"))

    def test_a_loaded_layout_changes_what_typing_produces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            swapped = dict(keymap.KEY_TO_SYMBOL)
            swapped["1"], swapped["q"] = swapped["q"], swapped["1"]
            path.write_text(
                json.dumps({"name": "測試配置", "keys": swapped}, ensure_ascii=False),
                encoding="utf-8",
            )

            problem = keymap.load_layout(path)

            self.assertEqual("", problem)
            self.assertEqual("ㄆ", keymap.symbol_for_key("1"))
            self.assertEqual("測試配置", keymap.active_layout_name())

    def test_libchewing_still_receives_da_qian_keys(self) -> None:
        # 這是整個功能最容易出錯的地方。keys_for_reading 送出的字元是給
        # libchewing 的 handle_Default，而那個 context 用的是它自己的大千鍵盤。
        # 跟著使用者的配置走，每個讀音都會查到錯的候選，而且不會有任何例外。
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            swapped = dict(keymap.KEY_TO_SYMBOL)
            swapped["1"], swapped["q"] = swapped["q"], swapped["1"]
            path.write_text(json.dumps({"keys": swapped}), encoding="utf-8")

            before = keymap.keys_for_reading("ㄅㄨˋ")
            keymap.load_layout(path)
            after = keymap.keys_for_reading("ㄅㄨˋ")

            self.assertEqual(before, after)
            self.assertEqual("1j4", after)

    def test_a_broken_layout_falls_back_and_explains_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            incomplete = dict(keymap.KEY_TO_SYMBOL)
            del incomplete["1"]
            path.write_text(json.dumps({"keys": incomplete}), encoding="utf-8")

            problem = keymap.load_layout(path)

            self.assertIn("ㄅ", problem)
            # 打不出中文比鍵位不對嚴重得多，所以壞掉的配置退回內建大千。
            self.assertEqual("ㄅ", keymap.symbol_for_key("1"))

    def test_a_damaged_file_does_not_stop_the_input_method_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            path.write_text("{not json", encoding="utf-8")

            problem = keymap.load_layout(path)

            self.assertTrue(problem)
            self.assertEqual("ㄅ", keymap.symbol_for_key("1"))

    def test_active_layout_cannot_be_mutated_from_outside(self) -> None:
        keymap.active_layout()["1"] = "ㄥ"
        self.assertEqual("ㄅ", keymap.symbol_for_key("1"))


if __name__ == "__main__":
    unittest.main()
