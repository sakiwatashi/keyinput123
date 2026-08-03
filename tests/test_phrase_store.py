import os
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
            self.assertEqual("寫程式", loaded.exact(readings))
            self.assertEqual("", loaded.exact(readings[:1]))
            # 「程式」不再被順手學走。這條刻意改掉：舊行為把每個子字串都學
            # 起來，一句十二字的話就產生約 66 筆，使用者的詞庫因此長到 6912
            # 筆、477 KB，其中大半是跨詞邊界的碎片。像「程式」這種常用詞本來
            # 就在內建詞庫裡，不需要個人學習提供。真正需要單獨記住的部分，
            # 由呼叫端以 extra_spans 明確指定。
            self.assertEqual((0, ""), loaded.best_suffix(readings[1:]))

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


class LearnScopeTest(unittest.TestCase):
    """learn() must not manufacture every substring of a sentence.

    The old behaviour learned width 2..12 at every position, so one
    twelve-character sentence produced about 66 entries. A real store reached
    6912 entries and 477 KB, roughly half of it fragments straddling word
    boundaries that nobody would type on purpose.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "phrases.json")

    def test_learns_only_the_whole_span_by_default(self) -> None:
        store = PhraseStore(self.path)
        store.learn(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ", "ㄅㄤˋ"], "我們好棒")
        self.assertEqual(1, len(store._entries))
        self.assertEqual("我們好棒", store.exact(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ", "ㄅㄤˋ"]))
        # A fragment across the word boundary must not have been invented.
        self.assertEqual("", store.exact(["ㄇㄣ˙", "ㄏㄠˇ"]))

    def test_named_spans_are_learned_as_well(self) -> None:
        """The part the user hand-corrected has to work on its own later."""
        store = PhraseStore(self.path)
        store.learn(
            ["ㄨㄛˇ", "ㄇㄛˊ", "ㄨˋ", "ㄌㄧㄝˋ", "ㄖㄣˊ"],
            "我魔物獵人",
            extra_spans=[(1, 5)],
        )
        self.assertEqual("魔物獵人", store.exact(["ㄇㄛˊ", "ㄨˋ", "ㄌㄧㄝˋ", "ㄖㄣˊ"]))
        self.assertEqual(2, len(store._entries))

    def test_a_twelve_character_sentence_stays_one_entry(self) -> None:
        readings = [f"ㄗ{index}" for index in range(12)]
        store = PhraseStore(self.path)
        store.learn(readings, "一二三四五六七八九十百千")
        self.assertEqual(1, len(store._entries), "又在製造子字串了")


class PruneRedundantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "phrases.json")

    def test_removes_entries_contained_in_a_longer_one(self) -> None:
        store = PhraseStore(self.path)
        store.learn(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ"], "我們好")
        store.learn(["ㄇㄣ˙", "ㄏㄠˇ"], "們好")
        self.assertEqual(2, len(store._entries))
        removed = store.prune_redundant()
        self.assertEqual(1, removed)
        self.assertEqual("我們好", store.exact(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ"]))
        self.assertEqual("", store.exact(["ㄇㄣ˙", "ㄏㄠˇ"]))

    def test_keeps_a_short_entry_that_is_not_contained(self) -> None:
        store = PhraseStore(self.path)
        store.learn(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ"], "我們好")
        store.learn(["ㄉㄧㄢˋ", "ㄏㄨㄚˋ"], "電話")
        self.assertEqual(0, store.prune_redundant())
        self.assertEqual("電話", store.exact(["ㄉㄧㄢˋ", "ㄏㄨㄚˋ"]))

    def test_removes_sliding_windows_of_a_longer_sentence(self) -> None:
        """Containment cannot reach maximum-width entries; nothing contains them.

        A sentence longer than MAX_PHRASE_LENGTH used to leave a chain of
        twelve-character windows, each overlapping the next by eleven. One real
        store carried 119 of them.
        """
        store = PhraseStore(self.path)
        sentence = "我要跟微軟一樣是右邊才是可編輯的"
        readings = [f"ㄗ{index}" for index in range(len(sentence))]
        for start in range(len(sentence) - 12 + 1):
            store._entries[" ".join(readings[start : start + 12])] = (
                sentence[start : start + 12]
            )
        self.assertGreater(len(store._entries), 1)
        store.prune_redundant()
        self.assertEqual(0, len(store._entries), "滑動視窗殘留")

    def test_keeps_a_deliberate_maximum_length_phrase(self) -> None:
        """A phrase typed on purpose has no neighbour offset by one syllable."""
        store = PhraseStore(self.path)
        readings = [f"ㄗ{index}" for index in range(12)]
        store.learn(readings, "一二三四五六七八九十百千")
        store.learn([f"ㄏ{index}" for index in range(4)], "另外一詞")
        self.assertEqual(0, store.prune_redundant())
        self.assertEqual(2, len(store._entries))

    def test_same_readings_but_different_text_is_kept(self) -> None:
        """Only an aligned match is redundant; a different choice is not."""
        store = PhraseStore(self.path)
        store.learn(["ㄨㄛˇ", "ㄇㄣ˙", "ㄏㄠˇ"], "我們好")
        store.learn(["ㄇㄣ˙", "ㄏㄠˇ"], "門號")
        self.assertEqual(0, store.prune_redundant())
        self.assertEqual("門號", store.exact(["ㄇㄣ˙", "ㄏㄠˇ"]))

if __name__ == "__main__":
    unittest.main()
