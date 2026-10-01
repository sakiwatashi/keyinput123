"""The bundled bigram model loads, answers correctly, and fails soft."""

from __future__ import annotations

import gzip
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core import bigram_model
from bopomofo_core.bigram_model import META_PATH, MODEL_PATH, BigramModel
from bopomofo_core.phrase_decoder import decode_phrase_lattice
from bopomofo_core.reading_phrase_lexicon import ReadingPhraseLexicon

LOG10 = math.log(10)


class BundledModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = BigramModel()

    def test_the_bundled_files_are_there_and_load(self) -> None:
        # Without this every language-model test below would pass against the
        # frequency-only fallback and verify nothing.
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        self.assertEqual("CC-BY-4.0", meta["license"])
        self.assertGreater(meta["bigrams"], 7_000_000)
        self.assertTrue(self.model.knows("一下"))

    def test_values_match_the_source(self) -> None:
        # Spot values from libchewing-data's bigram_p50.arpa at the pinned commit.
        self.assertAlmostEqual(-2.164, self.model.unigram_ln("是") / LOG10, places=3)
        self.assertAlmostEqual(-3.8477, self.model.bigram_ln("是", "了") / LOG10, places=3)
        self.assertAlmostEqual(-1.4573, self.model.bigram_ln("試", "了") / LOG10, places=3)

    def test_unknown_words_and_unstored_pairs_are_none(self) -> None:
        self.assertIsNone(self.model.unigram_ln("不存在的詞彙XYZ"))
        self.assertIsNone(self.model.bigram_ln("試", "不存在的詞彙XYZ"))
        self.assertIsNone(self.model.bigram_ln("看看", "龘"))


class FailSoftTest(unittest.TestCase):
    def test_a_damaged_file_means_no_model_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / "bigram_model.bin.gz"
            with gzip.open(broken, "wb") as handle:
                handle.write(b"not a model")
            saved = (bigram_model.MODEL_PATH, bigram_model._SHARED, bigram_model._LOADED)
            try:
                bigram_model.MODEL_PATH = broken
                bigram_model._SHARED, bigram_model._LOADED = None, False
                self.assertIsNone(bigram_model.shared_model(),
                                  "壞掉的模型檔應該讓輸入法退回沒有模型的算法，不是起不來")
            finally:
                bigram_model.MODEL_PATH, bigram_model._SHARED, bigram_model._LOADED = saved

    def test_a_truncated_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            truncated = Path(directory) / "bigram_model.bin.gz"
            with gzip.open(MODEL_PATH, "rb") as source:
                head = source.read(1 << 20)
            with gzip.open(truncated, "wb") as handle:
                handle.write(head)
            with self.assertRaises(ValueError):
                BigramModel(truncated)


class ReadingShareTest(unittest.TestCase):
    def test_polyphone_shares_follow_the_reading(self) -> None:
        lexicon = ReadingPhraseLexicon()
        # 還 is overwhelmingly ㄏㄞˊ; the model's frequency for 還 must not let
        # it beat 玄 under ㄒㄩㄢˊ.
        self.assertGreater(lexicon.reading_share(["ㄏㄞˊ"], "還"), 0.9)
        self.assertLess(lexicon.reading_share(["ㄒㄩㄢˊ"], "還"), 0.01)
        self.assertEqual(1.0, lexicon.reading_share(["ㄕˋ"], "是"))


class _ToyModel:
    """Two readings, two words each: enough to watch context flip a choice."""

    lam = 0.6
    oov_offset = -21.0
    log_floor = math.log(0.4)

    def __init__(self, unigrams, bigrams):
        self._u = {w: lp * LOG10 for w, lp in unigrams.items()}
        self._b = {k: lp * LOG10 for k, lp in bigrams.items()}

    def unigram_ln(self, word):
        return self._u.get(word)

    def bigram_ln(self, previous, word):
        return self._b.get((previous, word))


class LanguageModelDecodingTest(unittest.TestCase):
    """我試了一下: 是 is far more common than 試, but 了 after 是 is rare."""

    READINGS = ["ㄨㄛˇ", "ㄕˋ", "ㄌㄜ˙"]
    WORDS = {
        ("ㄨㄛˇ",): {"我": 1},
        ("ㄕˋ",): {"是": 1, "試": 1},
        ("ㄌㄜ˙",): {"了": 1},
    }
    UNIGRAMS = {"我": -2.27, "是": -2.16, "試": -3.71, "了": -2.09}
    BIGRAMS = {("我", "是"): -2.67, ("我", "試"): -3.47, ("是", "了"): -3.85, ("試", "了"): -1.46}

    def decode(self, model, personal=("", False)):
        lookup = lambda readings: list(self.WORDS.get(tuple(readings), {}))
        weight = lambda readings, phrase: self.WORDS.get(tuple(readings), {}).get(phrase, 0)
        spans = decode_phrase_lattice(
            self.READINGS, "我是了", [False] * 3, lookup, weight,
            lambda readings, context: personal, language_model=model,
        )
        return "".join(span.text for span in spans)

    def test_without_context_the_common_character_wins(self) -> None:
        # Premise: drop the bigrams and 是 must win, or the next test proves nothing.
        self.assertEqual("我是了", self.decode(_ToyModel(self.UNIGRAMS, {})))

    def test_the_following_word_brings_back_the_rarer_character(self) -> None:
        self.assertEqual("我試了", self.decode(_ToyModel(self.UNIGRAMS, self.BIGRAMS)))

    def test_a_personal_phrase_still_wins_its_own_span(self) -> None:
        self.WORDS[("ㄨㄛˇ", "ㄕˋ")] = {}
        try:
            got = self.decode(_ToyModel(self.UNIGRAMS, self.BIGRAMS), personal=("", False))
            self.assertEqual("我試了", got)
            lookup_personal = lambda readings, context: (
                ("我是", False) if readings == ["ㄨㄛˇ", "ㄕˋ"] else ("", False)
            )
            lookup = lambda readings: list(self.WORDS.get(tuple(readings), {}))
            weight = lambda readings, phrase: 0
            spans = decode_phrase_lattice(
                self.READINGS, "我是了", [False] * 3, lookup, weight, lookup_personal,
                language_model=_ToyModel(self.UNIGRAMS, self.BIGRAMS),
            )
            self.assertEqual("我是了", "".join(s.text for s in spans),
                             "使用者自己學過的詞一定要贏得它自己的那一段")
        finally:
            del self.WORDS[("ㄨㄛˇ", "ㄕˋ")]

    def test_split_words_are_regrouped_into_lexicon_words(self) -> None:
        # The model can decode 層數 as 層|數; the input method needs to see the word.
        readings = ["ㄘㄥˊ", "ㄕㄨˋ"]
        words = {("ㄘㄥˊ",): {"層": 1}, ("ㄕㄨˋ",): {"數": 1}, ("ㄘㄥˊ", "ㄕㄨˋ"): {"層數": 1}}
        model = _ToyModel({"層": -3.79, "數": -3.6}, {("層", "數"): -1.0})
        spans = decode_phrase_lattice(
            readings, "層數", [False, False],
            lambda r: list(words.get(tuple(r), {})), lambda r, p: words.get(tuple(r), {}).get(p, 0),
            lambda r, c: ("", False), language_model=model,
        )
        self.assertEqual([(0, 2, "層數")], [(s.start, s.end, s.text) for s in spans])


if __name__ == "__main__":
    unittest.main()
