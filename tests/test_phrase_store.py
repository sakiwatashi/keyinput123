import tempfile
import unittest
from pathlib import Path

from bopomofo_core.phrase_store import PhraseStore


class PhraseStoreTests(unittest.TestCase):
    def test_learns_multi_length_phrases_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phrases.json"
            readings = ["ㄒㄧㄝˇ", "ㄔㄥˊ", "ㄕˋ"]
            PhraseStore(path).learn(readings, "寫程式")

            loaded = PhraseStore(path)
            self.assertEqual((3, "寫程式"), loaded.best_suffix(readings))
            self.assertEqual((2, "程式"), loaded.best_suffix(readings[1:]))
            self.assertEqual("寫程式", loaded.exact(readings))
            self.assertEqual("", loaded.exact(readings[:1]))

    def test_longest_matching_suffix_wins(self) -> None:
        store = PhraseStore()
        store.learn(["ㄕㄨˋ", "ㄧㄝˋ"], "樹葉")
        store.learn(["ㄧˊ", "ㄆㄧㄢˋ", "ㄕㄨˋ", "ㄧㄝˋ"], "一片樹葉")
        self.assertEqual(
            (4, "一片樹葉"),
            store.best_suffix(["ㄧˊ", "ㄆㄧㄢˋ", "ㄕㄨˋ", "ㄧㄝˋ"]),
        )

    def test_mismatched_reading_and_text_is_ignored(self) -> None:
        store = PhraseStore()
        store.learn(["ㄗˋ", "ㄉㄧㄢˇ"], "字典庫")
        self.assertEqual((0, ""), store.best_suffix(["ㄗˋ", "ㄉㄧㄢˇ"]))

    def test_corrupt_file_is_preserved_and_does_not_block_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phrases.json"
            path.write_text("{incomplete", encoding="utf-8")

            store = PhraseStore(path)

            self.assertEqual((0, ""), store.best_suffix(["reading-a", "reading-b"]))
            self.assertFalse(path.exists())
            self.assertEqual(1, len(list(path.parent.glob("phrases.corrupt-*.json"))))

    def test_save_is_atomic_and_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phrases.json"
            PhraseStore(path).learn(["reading-a", "reading-b"], "葉樹")

            self.assertTrue(path.exists())
            self.assertEqual([], list(path.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
