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


class ExtraPhraseTests(unittest.TestCase):
    """上游詞庫缺席的能產組合。

    「這座城市」打成「蔗作城市」不是排序問題——詞庫裡根本沒有「這座」，只有
    「蔗作」（146）。指示詞加量詞是能產格位，64 組裡缺 21 組，包括「每個」
    「哪個」「這台」「那次」這些天天在用的。
    """

    def setUp(self) -> None:
        self.lexicon = ReadingPhraseLexicon()

    def test_a_missing_productive_combination_is_supplied(self) -> None:
        for reading, phrase in (
            (["ㄓㄜˋ", "ㄗㄨㄛˋ"], "這座"),
            (["ㄇㄟˇ", "ㄍㄜˋ"], "每個"),
            (["ㄋㄚˋ", "ㄘˋ"], "那次"),
            (["ㄓㄜˋ", "ㄓㄤˉ"], "這張"),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase, self.lexicon.candidates(reading)[0])

    def test_the_supplied_word_outweighs_the_noise_it_replaces(self) -> None:
        # 蔗作 是上游唯一的答案，權重 146。補的詞要贏得過它。
        reading = ["ㄓㄜˋ", "ㄗㄨㄛˋ"]
        self.assertGreater(
            self.lexicon.weight(reading, "這座"),
            self.lexicon.weight(reading, "蔗作"),
        )

    def test_a_combination_the_grammar_does_not_allow_is_not_supplied(self) -> None:
        # 格位能產不代表每一格都成立。「麼」只接這／那／怎，沒有「哪麼」。
        self.assertEqual(0, self.lexicon.weight(["ㄋㄚˇ", "ㄇㄜ˙"], "哪麼"))

    def test_upstream_weights_are_not_overwritten(self) -> None:
        # 詞庫已經有的組合不補，免得用一個扁平的數字蓋掉真實的詞頻。
        reading = ["ㄓㄜˋ", "ㄍㄜˋ"]
        self.assertEqual("這個", self.lexicon.candidates(reading)[0])
        self.assertGreater(self.lexicon.weight(reading, "這個"), 100_000)

    def test_a_missing_file_falls_back_to_upstream_only(self) -> None:
        plain = ReadingPhraseLexicon(extra_path=Path("no-such-extra.json"))
        self.assertEqual(0, plain.weight(["ㄓㄜˋ", "ㄗㄨㄛˋ"], "這座"))


class WeightAndOrderAgreeTests(unittest.TestCase):
    """candidates() 的順序必須跟 weight() 的數字一致。

    這兩個答案曾經是兩份各自實作的程式碼。結果是權重改對了而順序沒跟著改：
    「這裡」的 weight 已經贏過「這裏」，按 ↓ 卻還是「這裏」排第一。這一組
    測試盯的不是某個詞，而是「兩邊會不會再度分家」。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = ReadingPhraseLexicon()

    def sample_keys(self, count: int) -> list[str]:
        # 跨越整份索引取樣，而不是只看前面幾筆——降權與破音字散在各處。
        keys = sorted(self.lexicon._entries)
        step = max(1, len(keys) // count)
        return keys[::step][:count]

    def test_candidate_order_never_contradicts_the_weight(self) -> None:
        checked = 0
        for key in self.sample_keys(400):
            readings = key.split(" ")
            candidates = self.lexicon.candidates(readings)
            weights = [self.lexicon.weight(readings, c) for c in candidates]
            for earlier, later in zip(weights, weights[1:]):
                self.assertGreaterEqual(
                    earlier,
                    later,
                    f"{key} 的候選順序跟權重不一致：{list(zip(candidates, weights))}",
                )
            checked += len(candidates)
        self.assertGreater(checked, 500, "取樣太少，這個測試沒有真的在看東西")

    def test_a_demoted_variant_is_ordered_by_its_demoted_weight(self) -> None:
        # 具體的一組：異體字降權之後，順序也要跟著換。
        readings = ["ㄔˉ"]
        candidates = self.lexicon.candidates(readings)
        self.assertIn("吃", candidates)
        self.assertIn("喫", candidates)
        self.assertLess(candidates.index("吃"), candidates.index("喫"))
        self.assertGreater(
            self.lexicon.weight(readings, "吃"),
            self.lexicon.weight(readings, "喫"),
        )

    def test_a_supplied_word_is_ordered_by_its_supplied_weight(self) -> None:
        # 補進來的詞也要進到同一條排序裡，不是附在最後面。
        readings = ["ㄓㄜˋ", "ㄗㄨㄛˋ"]
        candidates = self.lexicon.candidates(readings)
        self.assertIn("這座", candidates)
        self.assertIn("蔗作", candidates)
        self.assertLess(candidates.index("這座"), candidates.index("蔗作"))


class RowCacheTests(unittest.TestCase):
    """快取只准影響速度，不准影響答案。"""

    def test_the_cache_returns_the_same_answer_as_a_cold_lookup(self) -> None:
        warm = ReadingPhraseLexicon()
        for key in ["ㄅㄨˋ", "ㄕˋ", "ㄔˉ", "ㄓㄜˋ ㄗㄨㄛˋ", "ㄨㄛˇ ㄇㄣ˙"]:
            readings = key.split(" ")
            cold = ReadingPhraseLexicon().candidates(readings)
            self.assertEqual(cold, warm.candidates(readings))
            self.assertEqual(cold, warm.candidates(readings), "第二次查就變了")

    def test_the_cache_is_bounded(self) -> None:
        # 輸入法是長時間執行的行程。無上限的快取就是慢性洩漏。
        from bopomofo_core.reading_phrase_lexicon import ROW_CACHE_LIMIT

        lexicon = ReadingPhraseLexicon()
        for key in sorted(lexicon._entries)[: ROW_CACHE_LIMIT * 3]:
            lexicon.candidates(key.split(" "))
        self.assertLessEqual(len(lexicon._row_cache), ROW_CACHE_LIMIT)
        self.assertGreater(len(lexicon._row_cache), 0, "根本沒在快取")


class ToneSandhiTests(unittest.TestCase):
    """「一」「不」的兩種唸法都要查得到詞。

    「幫我一個忙」打出來是「幫我一各忙」。詞庫把「一個」只收在本調 ㄧˉ ㄍㄜˋ
    底下，而這個詞唸出來是 yí ge——照著唸打 ㄧˊ ㄍㄜˋ，兩字詞一個都查不到，
    只能逐字拼，「各」就有機會冒出來。

    反方向缺得更嚴重：「不是」「不要」在語料裡只收了變調的 ㄅㄨˊ，而本調
    ㄅㄨˋ ㄕˋ、ㄅㄨˋ ㄧㄠˋ 查下去一個詞都沒有——本調正是學校教的打法。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = ReadingPhraseLexicon()

    def test_the_spoken_tone_finds_the_word(self) -> None:
        # 一 在四聲前唸 ㄧˊ
        self.assertIn("一個", self.lexicon.candidates(["ㄧˊ", "ㄍㄜˋ"]))
        self.assertIn(
            "一個人", self.lexicon.candidates(["ㄧˊ", "ㄍㄜˋ", "ㄖㄣˊ"])
        )
        # 一 在一二三聲前唸 ㄧˋ
        self.assertIn("一一", self.lexicon.candidates(["ㄧˋ", "ㄧˉ"]))
        # 不 只在四聲前變，語料本來就收了，這裡確認沒被弄壞
        self.assertIn("不是", self.lexicon.candidates(["ㄅㄨˊ", "ㄕˋ"]))

    def test_the_base_tone_finds_the_word(self) -> None:
        # 學校教的是本調，很多人就是這樣打。這幾個在語料裡本調底下是空的。
        self.assertIn("不是", self.lexicon.candidates(["ㄅㄨˋ", "ㄕˋ"]))
        self.assertIn("不要", self.lexicon.candidates(["ㄅㄨˋ", "ㄧㄠˋ"]))
        self.assertIn("一個", self.lexicon.candidates(["ㄧˉ", "ㄍㄜˋ"]))
        self.assertIn("一定", self.lexicon.candidates(["ㄧˉ", "ㄉㄧㄥˋ"]))

    def test_a_re_spelled_word_does_not_outrank_the_word_that_owns_the_sound(
        self,
    ) -> None:
        """「不對」唸 bú duì，本調寫法撞到「部隊」——而部隊沒有變調，那就是它
        唯一的唸法。補進來的目的是讓詞打得出來，不是讓它排第一。"""
        self.assertEqual("部隊", self.lexicon.candidates(["ㄅㄨˋ", "ㄉㄨㄟˋ"])[0])
        self.assertIn("不對", self.lexicon.candidates(["ㄅㄨˋ", "ㄉㄨㄟˋ"]))
        self.assertEqual("步調", self.lexicon.candidates(["ㄅㄨˋ", "ㄉㄧㄠˋ"])[0])
        self.assertIn("不掉", self.lexicon.candidates(["ㄅㄨˋ", "ㄉㄧㄠˋ"]))

    def test_the_ordinal_one_is_left_alone(self) -> None:
        # 第一名唸 dì-yī-míng，不是 dì-yì-míng。序數的一不變調，把它當成會變調
        # 的，產生出來的就是沒有人會這樣唸的讀音。
        for phrase in ("第一名", "第一次", "第十一屆"):
            for key, words in self._added().items():
                self.assertNotIn(
                    phrase, words, f"{phrase} 不該有變調唸法（{key}）"
                )

    def test_the_month_reading_does_not_displace_the_real_sandhi_word(self) -> None:
        # 一月唸 yī-yuè；ㄧˊ ㄩㄝˋ 是「一躍」的唸法，不能被一月佔走。
        self.assertEqual("一躍", self.lexicon.candidates(["ㄧˊ", "ㄩㄝˋ"])[0])

    def _added(self) -> dict:
        import json
        from bopomofo_core.reading_phrase_lexicon import DEFAULT_SANDHI

        return json.loads(DEFAULT_SANDHI.read_text(encoding="utf-8"))["entries"]

    def test_a_missing_file_falls_back_to_the_base_tone_only(self) -> None:
        plain = ReadingPhraseLexicon(sandhi_path=Path("no-such-sandhi.json"))
        self.assertNotIn("一個", plain.candidates(["ㄧˊ", "ㄍㄜˋ"]))
        self.assertEqual([], plain.candidates(["ㄅㄨˋ", "ㄕˋ"]))
        self.assertIn("一個", plain.candidates(["ㄧˉ", "ㄍㄜˋ"]))


class TaiwanPreferredTests(unittest.TestCase):
    """同音不同寫法時，台灣的寫法要排前面。

    上游語料是大陸語料轉製的，同一個詞的兩種寫法都在裡面，而大陸那一種帶著
    全部的詞頻：賬戶 16605 對 帳戶 2876，界面 14436 對 介面 588。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = ReadingPhraseLexicon()

    def test_the_taiwan_spelling_comes_first(self) -> None:
        for readings, expected in (
            (["ㄐㄧㄝˋ", "ㄇㄧㄢˋ"], "介面"),
            (["ㄓㄤˋ", "ㄏㄨˋ"], "帳戶"),
            (["ㄐㄧㄝˊ", "ㄓㄤˋ"], "結帳"),
            (["ㄓㄨㄢˇ", "ㄓㄤˋ"], "轉帳"),
            (["ㄕㄣˉ", "ㄈㄣˋ"], "身分"),
            (["ㄕㄣˉ", "ㄈㄣˋ", "ㄓㄥˋ"], "身分證"),
            (["ㄧˋ", "ㄉㄚˋ", "ㄌㄧˋ"], "義大利"),
            (["ㄇㄚˊ", "ㄅㄧˋ"], "麻痺"),
        ):
            self.assertEqual(
                expected,
                self.lexicon.candidates(readings, 1)[0],
                f"{' '.join(readings)} 的第一個候選不是台灣寫法",
            )

    def test_the_other_spelling_is_still_available(self) -> None:
        # 對調不是刪除。要打大陸寫法的人照樣選得到，只是不排第一。
        self.assertIn("界面", self.lexicon.candidates(["ㄐㄧㄝˋ", "ㄇㄧㄢˋ"]))
        self.assertIn("賬戶", self.lexicon.candidates(["ㄓㄤˋ", "ㄏㄨˋ"]))

    def test_a_same_sounding_word_that_is_already_correct_is_left_alone(self) -> None:
        """這一組是護欄，不是功能測試。

        用字級替換自動掃會炸：「下麵」會贏過「下面」，「錶面」會贏過「表面」。
        同音不代表同義，所以那份清單只收確認過整族都沒有例外的字。把它改成
        通則，這裡就會紅。
        """
        for readings, expected in (
            (["ㄒㄧㄚˋ", "ㄇㄧㄢˋ"], "下面"),
            (["ㄅㄧㄠˇ", "ㄇㄧㄢˋ"], "表面"),
            (["ㄓㄡˉ", "ㄉㄠˋ"], "周到"),
            (["ㄓˋ", "ㄘㄞˊ"], "制裁"),
            (["ㄓㄨㄢˉ", "ㄓㄨˋ"], "專注"),
            (["ㄏㄨㄟˊ", "ㄍㄨㄟˉ"], "回歸"),
            (["ㄊㄞˊ", "ㄨㄢˉ"], "台灣"),
            (["ㄊㄞˊ", "ㄅㄟˇ"], "台北"),
            (["ㄧˊ", "ㄈㄣˋ"], "一份"),
            (["ㄩㄝˋ", "ㄈㄣˋ"], "月份"),
            (["ㄍㄨˇ", "ㄈㄣˋ"], "股份"),
        ):
            self.assertEqual(
                expected,
                self.lexicon.candidates(readings, 1)[0],
                f"{' '.join(readings)} 本來就是對的，不該被改掉",
            )

    def test_a_missing_file_falls_back_to_the_corpus_order(self) -> None:
        plain = ReadingPhraseLexicon(taiwan_path=Path("no-such-taiwan.json"))
        self.assertEqual("界面", plain.candidates(["ㄐㄧㄝˋ", "ㄇㄧㄢˋ"], 1)[0])


class MissingVocabularyTests(unittest.TestCase):
    """詞庫整個沒收的常用詞。

    「玄幻」打出來是「玄換」，不是排序問題——ㄒㄩㄢˊ ㄏㄨㄢˋ 這個讀音底下
    一個候選都沒有，只能逐字拼，而「換」（33491）本來就壓過「幻」（1767）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.lexicon = ReadingPhraseLexicon()

    def test_the_word_can_be_typed(self) -> None:
        for readings, expected in (
            (["ㄒㄩㄢˊ", "ㄏㄨㄢˋ"], "玄幻"),
            (["ㄒㄧㄡˉ", "ㄒㄧㄢˉ"], "修仙"),
            (["ㄈㄨˊ", "ㄎㄨㄥˉ"], "浮空"),
            (["ㄧㄤˇ", "ㄊㄤˇ"], "仰躺"),
        ):
            self.assertEqual(
                expected,
                self.lexicon.candidates(readings, 1)[0],
                f"{' '.join(readings)} 打不出「{expected}」",
            )

    def test_nothing_was_displaced(self) -> None:
        # 這幾個讀音鍵原本一個候選都沒有，所以補進去只能是增加。這一條盯的是
        # 「別把補詞變成蓋掉別人」——往清單裡加一個已經有主人的讀音，這裡會紅。
        plain = ReadingPhraseLexicon(extra_path=Path("no-such-extra.json"))
        for readings in (
            ["ㄒㄩㄢˊ", "ㄏㄨㄢˋ"],
            ["ㄒㄧㄡˉ", "ㄒㄧㄢˉ"],
            ["ㄈㄨˊ", "ㄎㄨㄥˉ"],
            ["ㄧㄤˇ", "ㄊㄤˇ"],
        ):
            self.assertEqual(
                [], plain.candidates(readings), f"{' '.join(readings)} 原本就有詞"
            )
