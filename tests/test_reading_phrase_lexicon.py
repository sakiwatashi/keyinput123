import tempfile
import unittest
from pathlib import Path

from bopomofo_core.reading_phrase_lexicon import ReadingPhraseLexicon


class ReadingPhraseLexiconTests(unittest.TestCase):
    def test_bundled_index_contains_common_taiwan_phrases(self):
        lexicon = ReadingPhraseLexicon()
        self.assertGreater(lexicon.entry_count, 100_000)
        self.assertEqual(
            lexicon.candidates(["ㄘㄥˊ", "ㄕㄨˋ"])[0], "層數"
        )
        self.assertEqual(
            lexicon.candidates(["ㄐㄧㄠˋ", "ㄍㄠˉ"])[0], "較高"
        )
        self.assertIn(
            "演算法",
            lexicon.candidates(["ㄧㄢˇ", "ㄙㄨㄢˋ", "ㄈㄚˇ"]),
        )
        self.assertIn("新句", lexicon.candidates(["ㄒㄧㄣˉ", "ㄐㄩˋ"]))
        self.assertGreater(
            lexicon.weight(["ㄇㄟˇ"], "每"),
            lexicon.weight(["ㄇㄟˇ"], "美"),
        )
        self.assertGreater(
            lexicon.weight(["ㄒㄧㄣˉ"], "新"),
            lexicon.weight(["ㄒㄧㄣˉ"], "心"),
        )

    def test_wrong_alternate_reading_cannot_borrow_a_common_phrase(self):
        lexicon = ReadingPhraseLexicon()
        self.assertNotIn(
            "貝殼", lexicon.candidates(["ㄅㄟˋ", "ㄑㄩㄝˋ"])
        )
        self.assertIn("貝殼", lexicon.candidates(["ㄅㄟˋ", "ㄎㄜˊ"]))

    def test_corrupt_or_missing_index_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = ReadingPhraseLexicon(Path(directory) / "missing.gz")
            self.assertEqual(missing.candidates(["ㄧˉ", "ㄍㄜ˙"]), [])


if __name__ == "__main__":
    unittest.main()
