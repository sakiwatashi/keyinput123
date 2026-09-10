import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "keymap_layout.py"
_spec = importlib.util.spec_from_file_location("keymap_layout_tool", _TOOL)
keymap_layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(keymap_layout)

from bopomofo_core import keymap  # noqa: E402


class InvertSymbolTableTests(unittest.TestCase):
    def test_a_clean_table_inverts(self) -> None:
        inverted, problem = keymap_layout.invert_symbol_table({"ㄅ": "1", "ㄆ": "q"})
        self.assertEqual("", problem)
        self.assertEqual({"1": "ㄅ", "q": "ㄆ"}, inverted)

    def test_two_symbols_on_one_key_names_the_key_and_both_symbols(self) -> None:
        # 反轉會默默吃掉其中一筆，驗證器接著只會說「打不出 ㄆ」——正確，但完全
        # 沒指到使用者做錯的那件事。訊息必須說出撞的是哪個鍵。
        inverted, problem = keymap_layout.invert_symbol_table({"ㄅ": "1", "ㄆ": "1"})
        self.assertIsNone(inverted)
        self.assertIn("1", problem)
        self.assertIn("ㄅ", problem)
        self.assertIn("ㄆ", problem)

    def test_a_multi_character_key_is_named(self) -> None:
        inverted, problem = keymap_layout.invert_symbol_table({"ㄅ": "ctrl+1"})
        self.assertIsNone(inverted)
        self.assertIn("ㄅ", problem)


class ApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / "keymap.json"

    def tearDown(self) -> None:
        keymap.load_layout(self.root / "gone.json")
        self.temp.cleanup()

    def _candidate(self, payload) -> Path:
        path = self.root / "candidate.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _symbol_table(self) -> dict[str, str]:
        return {symbol: key for key, symbol in keymap.KEY_TO_SYMBOL.items()}

    def test_a_valid_symbol_table_is_written_without_a_bom(self) -> None:
        table = self._symbol_table()
        table["ㄅ"], table["ㄆ"] = table["ㄆ"], table["ㄅ"]

        result = keymap_layout.apply(
            self._candidate({"name": "測試", "symbols": table}), self.target
        )

        self.assertTrue(result["ok"], result)
        self.assertNotEqual(b"\xef\xbb\xbf", self.target.read_bytes()[:3])
        written = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual("ㄆ", written["keys"]["1"])

    def test_a_rejected_layout_leaves_the_existing_file_untouched(self) -> None:
        good = self._symbol_table()
        keymap_layout.apply(self._candidate({"name": "好的", "symbols": good}), self.target)
        before = self.target.read_bytes()

        bad = self._symbol_table()
        bad["ㄆ"] = bad["ㄅ"]
        result = keymap_layout.apply(
            self._candidate({"name": "壞的", "symbols": bad}), self.target
        )

        self.assertFalse(result["ok"])
        self.assertEqual(before, self.target.read_bytes())

    def test_an_incomplete_layout_is_refused(self) -> None:
        table = self._symbol_table()
        del table["ㄅ"]
        result = keymap_layout.apply(self._candidate({"symbols": table}), self.target)
        self.assertFalse(result["ok"])
        self.assertIn("ㄅ", result["error"])

    def test_the_file_format_shape_is_also_accepted(self) -> None:
        # 手寫的 keymap.json 用的是「按鍵 → 符號」，跟控制台送的形狀相反。
        result = keymap_layout.apply(
            self._candidate({"keys": dict(keymap.KEY_TO_SYMBOL)}), self.target
        )
        self.assertTrue(result["ok"], result)


class DumpTests(unittest.TestCase):
    def test_symbol_order_is_stable_across_runs(self) -> None:
        # 用 set 產生順序，控制台每次開啟的列順序都不一樣，使用者找不到上次改
        # 過的那一列。
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            first = keymap_layout.dump(path)["symbols"]
            second = keymap_layout.dump(path)["symbols"]
        self.assertEqual(first, second)
        self.assertEqual(list(dict.fromkeys(keymap.KEY_TO_SYMBOL.values())), first)

    def test_a_broken_file_is_reported_rather_than_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "keymap.json"
            table = dict(keymap.KEY_TO_SYMBOL)
            del table["1"]
            path.write_text(json.dumps({"keys": table}), encoding="utf-8")

            result = keymap_layout.dump(path)

            self.assertIn("ㄅ", result["problem"])
            self.assertEqual("ㄅ", result["active"]["1"])
        keymap.load_layout(Path("gone.json"))


if __name__ == "__main__":
    unittest.main()
