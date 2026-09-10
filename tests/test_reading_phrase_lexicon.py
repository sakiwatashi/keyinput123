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


class VariantDemotionTests(unittest.TestCase):
    """簡轉繁留下的異體字不該贏過台灣慣用字。

    內建詞庫由簡體語料轉製，而轉換表把常用字映射到異體字，異體字因此繼承了常用
    字的全部詞頻：爲 211329 對 為 684、喫 65597 對 吃 805。實測後果是打「我要吃」
    得到「我要喫」、打「這裡」得到「這裏」。
    """

    def setUp(self) -> None:
        self.lexicon = ReadingPhraseLexicon()

    def test_the_common_form_outweighs_the_variant(self) -> None:
        for reading, common, variant in (
            (["ㄔˉ"], "吃", "喫"),
            (["ㄨㄟˊ"], "為", "爲"),
            (["ㄌㄧˇ"], "裡", "裏"),
            (["ㄑㄩㄣˊ"], "群", "羣"),
        ):
            with self.subTest(variant=variant):
                self.assertGreater(
                    self.lexicon.weight(reading, common),
                    self.lexicon.weight(reading, variant),
                )

    def test_a_phrase_containing_a_variant_is_demoted_too(self) -> None:
        # 設上限救不了這個：任何能壓過 爲(211329) 的上限都還是高過 吃飯(585)。
        # 所以降權用的是除法，比例縮放同時處理單字與詞組。
        reading = ["ㄔˉ", "ㄈㄢˋ"]
        self.assertGreater(
            self.lexicon.weight(reading, "吃飯"),
            self.lexicon.weight(reading, "喫飯"),
        )

    def test_the_candidate_order_follows_the_demoted_weight(self) -> None:
        # 權重改了、順序沒改，下游取第一個，「這裡」照樣打成「這裏」。這一條就是
        # 那個 bug 的守門員。
        self.assertEqual("這裡", self.lexicon.candidates(["ㄓㄜˋ", "ㄌㄧˇ"])[0])
        self.assertEqual("吃", self.lexicon.candidates(["ㄔˉ"])[0])

    def test_a_demoted_variant_stays_available(self) -> None:
        # 降權是排到後面，不是從詞庫刪掉。想打「喫」的人還是要打得出來。
        self.assertIn("喫", self.lexicon.candidates(["ㄔˉ"]))
        self.assertGreaterEqual(self.lexicon.weight(["ㄔˉ"], "喫"), 1)

    def test_readings_with_no_variant_keep_their_original_order(self) -> None:
        # 重排只在含降權字的讀音上發生，其他讀音一個字都不能動。
        plain = ReadingPhraseLexicon(demotions_path=Path("no-such-demotions.json"))
        for reading in (["ㄘㄥˊ", "ㄕㄨˋ"], ["ㄐㄧㄠˋ", "ㄍㄠˉ"], ["ㄕㄨˋ", "ㄧㄝˋ"]):
            with self.subTest(reading=reading):
                self.assertEqual(
                    plain.candidates(reading), self.lexicon.candidates(reading)
                )

    def test_a_missing_list_falls_back_to_the_old_behaviour(self) -> None:
        # 這份名單只調整排序。缺檔就是加這個功能之前的樣子，不該讓輸入法起不來。
        plain = ReadingPhraseLexicon(demotions_path=Path("no-such-demotions.json"))
        self.assertGreater(plain.weight(["ㄔˉ"], "喫"), plain.weight(["ㄔˉ"], "吃"))

    def test_a_damaged_list_is_ignored_rather_than_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "variant_demotions.json"
            path.write_text("{broken", encoding="utf-8")
            lexicon = ReadingPhraseLexicon(demotions_path=path)
            self.assertGreater(lexicon.entry_count, 100_000)
