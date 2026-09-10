import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.context_store import (
    MAX_CONTEXTS_PER_READING,
    ContextStore,
)


READING = ["ㄔㄥˊ", "ㄕˋ"]


class ContextStoreTests(unittest.TestCase):
    def test_the_same_reading_keeps_a_different_word_per_context(self) -> None:
        # 這是這個檔案存在的全部理由：選過一次「程式」不該讓「這座城市」壞掉。
        store = ContextStore()
        store.learn(READING, "程式", "寫")
        store.learn(READING, "城市", "座")

        self.assertEqual("程式", store.lookup(READING, "寫"))
        self.assertEqual("城市", store.lookup(READING, "座"))

    def test_an_unseen_context_matches_nothing(self) -> None:
        store = ContextStore()
        store.learn(READING, "程式", "寫")
        self.assertEqual("", store.lookup(READING, "座"))

    def test_relearning_the_same_context_replaces_it(self) -> None:
        store = ContextStore()
        store.learn(READING, "城市", "寫")
        store.learn(READING, "程式", "寫")
        self.assertEqual("程式", store.lookup(READING, "寫"))
        self.assertEqual({"寫": "程式"}, store.contexts_for(READING))

    def test_a_span_with_no_left_neighbour_is_not_filed_under_a_made_up_key(
        self,
    ) -> None:
        # 句首的跨度沒有左鄰字。硬給它一個 key，會讓所有句首的選擇擠進同一格，
        # 然後互相覆蓋——比沒有上下文更糟。
        store = ContextStore()
        store.learn(READING, "程式", "")
        self.assertEqual({}, store.contexts_for(READING))
        self.assertEqual("", store.lookup(READING, ""))

    def test_mismatched_reading_and_text_is_ignored(self) -> None:
        store = ContextStore()
        store.learn(READING, "程式碼", "寫")
        self.assertEqual({}, store.contexts_for(READING))

    def test_contexts_per_reading_are_capped_oldest_first(self) -> None:
        store = ContextStore()
        for index in range(MAX_CONTEXTS_PER_READING + 3):
            store.learn(READING, "程式", chr(0x4E00 + index))

        contexts = store.contexts_for(READING)
        self.assertEqual(MAX_CONTEXTS_PER_READING, len(contexts))
        self.assertNotIn(chr(0x4E00), contexts, "最舊的沒有被丟掉")
        self.assertIn(chr(0x4E00 + MAX_CONTEXTS_PER_READING + 2), contexts)

    def test_persists_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contexts.json"
            ContextStore(path).learn(READING, "程式", "寫")

            self.assertEqual("程式", ContextStore(path).lookup(READING, "寫"))
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual({"ㄔㄥˊ ㄕˋ": {"寫": "程式"}}, written)
            self.assertNotEqual(b"\xef\xbb\xbf", path.read_bytes()[:3])

    def test_a_damaged_file_costs_nothing_but_this_refinement(self) -> None:
        # phrases.json 才是不可取代的資料。這個檔壞掉只該讓輸入法退回原本的
        # 行為，不該讓它起不來。
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contexts.json"
            path.write_text("{broken", encoding="utf-8")

            store = ContextStore(path)

            self.assertEqual("", store.lookup(READING, "寫"))
            self.assertEqual(1, len(list(path.parent.glob("contexts.corrupt-*.json"))))

    def test_rubbish_entries_are_skipped_rather_than_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contexts.json"
            path.write_text(
                json.dumps(
                    {
                        "ㄔㄥˊ ㄕˋ": {"寫": "程式", "太長的上下文": "城市", "座": ""},
                        "壞掉的": "不是物件",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = ContextStore(path)

            self.assertEqual({"寫": "程式"}, store.contexts_for(READING))
            self.assertEqual(1, len(store))


if __name__ == "__main__":
    unittest.main()
