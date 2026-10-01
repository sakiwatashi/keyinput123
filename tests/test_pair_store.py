"""連字習慣：只記送出文字裡相鄰的漢字，並替詞網格的切法加分。"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.pair_store import MAX_PAIRS, STRENGTH, TRIM_TO, PairStore
from bopomofo_core.phrase_decoder import decode_phrase_lattice


class PairStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "pairs.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_counts_adjacent_han_characters_only(self) -> None:
        store = PairStore(self.path)
        store.record("現在是，用 AI 一個ㄅ")
        self.assertEqual(1, store.count("現在"))
        self.assertEqual(1, store.count("在是"))
        # 標點、英文、注音符號兩邊不是上下文。
        self.assertEqual(0, store.count("是用"))
        self.assertEqual(0, store.count("個ㄅ"))
        self.assertEqual(1, store.count("一個"))

    def test_bonus_includes_the_pair_across_the_span_boundary(self) -> None:
        store = PairStore(self.path)
        store.record("在是")
        # 「是」自己一段時，唯一能說明它的就是左邊的「在」。
        self.assertAlmostEqual(STRENGTH * math.log1p(1), store.bonus("在", "是"))
        self.assertEqual(0.0, store.bonus("在", "適"))
        self.assertEqual(0.0, store.bonus("", "是"))

    def test_bootstrap_uses_commit_counts(self) -> None:
        store = PairStore(self.path)
        store.bootstrap([("現在是", 3), ("一個", 1), ("壞", 0)])
        self.assertEqual(3, store.count("在是"))
        self.assertEqual(1, store.count("一個"))
        self.assertTrue(self.path.exists(), "預先學完要寫檔，否則下次啟動又重來一次")

    def test_survives_damage_and_round_trips(self) -> None:
        self.path.write_text("{ nope", encoding="utf-8")
        self.assertEqual(0, len(PairStore(self.path)))
        store = PairStore(self.path)
        store.record("現在是")
        store.flush(force=True)
        self.assertEqual(1, PairStore(self.path).count("在是"))

    def test_stays_bounded(self) -> None:
        store = PairStore(self.path)
        for index in range(MAX_PAIRS + 1):
            store._pairs[chr(0x4E00 + index % 20000) + chr(0x4E00 + index // 20000)] = 1
        store._pending = 1
        store.flush()
        self.assertLessEqual(len(store), TRIM_TO)


class PairScoreInLatticeTest(unittest.TestCase):
    """現在是用一個 -> 現在適用一個：沒有上下文時冷門的「適用」贏過常見的「是」。"""

    READINGS = ["ㄒㄧㄢˋ", "ㄗㄞˋ", "ㄕˋ", "ㄩㄥˋ"]
    WORDS = {
        ("ㄒㄧㄢˋ", "ㄗㄞˋ"): {"現在": 90000},
        ("ㄕˋ", "ㄩㄥˋ"): {"適用": 30000},
        ("ㄕˋ",): {"是": 600000, "適": 2000},
        ("ㄩㄥˋ",): {"用": 150000},
    }

    def decode(self, pair_score=None) -> str:
        lookup = lambda readings: list(self.WORDS.get(tuple(readings), {}))
        weight = lambda readings, phrase: self.WORDS.get(tuple(readings), {}).get(phrase, 0)
        spans = decode_phrase_lattice(
            self.READINGS, "現在是用", [False] * 4, lookup, weight,
            lambda readings, context: ("", False), pair_score=pair_score,
        )
        return "".join(span.text for span in spans)

    def test_without_the_users_habits_the_rare_word_wins(self) -> None:
        # 前提：這個例子本身要能重現問題，否則下一支測試什麼都沒驗。
        self.assertEqual("現在適用", self.decode())

    def test_the_users_habits_bring_back_the_common_character(self) -> None:
        store = PairStore()
        for _ in range(5):
            store.record("現在是")
            store.record("是用")
        self.assertEqual("現在是用", self.decode(store.bonus))


if __name__ == "__main__":
    unittest.main()
