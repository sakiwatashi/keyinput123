import unittest

from bopomofo_core.phrase_decoder import decode_phrase_lattice


class PhraseDecoderTests(unittest.TestCase):
    def test_single_character_frequency_can_resolve_a_word_boundary(self):
        phrases = {
            ("mei",): ["美", "每"],
            ("yu",): ["譽", "遇"],
            ("dao",): ["到"],
            ("mei", "yu"): ["美譽"],
            ("yu", "dao"): ["遇到"],
        }
        weights = {
            "美": 18573,
            "每": 20025,
            "譽": 1054,
            "遇": 2730,
            "到": 297457,
            "美譽": 920,
            "遇到": 49326,
        }

        spans = decode_phrase_lattice(
            ["mei", "yu", "dao"],
            "美遇到",
            [False, False, False],
            lambda readings: phrases.get(tuple(readings), []),
            lambda _readings, phrase: weights.get(phrase, 0),
            lambda _readings, _context: ("", False),
        )

        self.assertEqual("每遇到", "".join(span.text for span in spans))

    def setUp(self):
        self.entries = {
            ("r0", "r1"): [("層數", 500)],
            ("r2", "r3"): [("較高", 331)],
            ("r0", "r1", "r2"): [("錯誤句", 9999)],
        }

    def lookup(self, readings):
        return [value for value, _ in self.entries.get(tuple(readings), [])]

    def weight(self, readings, phrase):
        return dict(self.entries.get(tuple(readings), [])).get(phrase, 0)

    def test_combines_multiple_words_instead_of_requiring_a_whole_sentence(self):
        spans = decode_phrase_lattice(
            ["r0", "r1", "r2", "r3"],
            "曾恕叫高",
            [False] * 4,
            self.lookup,
            self.weight,
            lambda _readings, _context: ("", False),
        )
        self.assertEqual("".join(span.text for span in spans), "層數較高")

    def test_explicit_selection_is_a_hard_boundary(self):
        spans = decode_phrase_lattice(
            ["r0", "r1", "r2", "r3"],
            "曾恕叫高",
            [True, False, False, False],
            self.lookup,
            self.weight,
            lambda _readings, _context: ("", False),
        )
        self.assertEqual("".join(span.text for span in spans), "曾恕較高")

    def test_personal_phrase_beats_a_bundled_phrase(self):
        spans = decode_phrase_lattice(
            ["r0", "r1"],
            "曾恕",
            [False, False],
            self.lookup,
            self.weight,
            lambda readings, _context: ("自訂", False) if readings == ["r0", "r1"] else ("", False),
        )
        self.assertEqual("".join(span.text for span in spans), "自訂")
        self.assertTrue(spans[0].personal)

    def test_personal_phrase_cannot_dismantle_a_stronger_neighbour(self):
        """A pair learned in one context must not rewrite a stronger word.

        Reproduces 電話一 coming out as 店化一: 化一 had been learned from some
        other sentence, and because personal origin outranked every weight, it
        took the 話 away from 電話 (50001) and left 電 to fall back to 店.
        """
        phrases = {
            ("dian",): ["店", "電"],
            ("hua",): ["話", "化"],
            ("yi",): ["一"],
            ("dian", "hua"): ["電話", "電化"],
            ("hua", "yi"): ["畫一", "劃一"],
        }
        weights = {
            "店": 12541,
            "話": 58786,
            "一": 135314,
            "電話": 50001,
            "電化": 647,
            "畫一": 120,
            "劃一": 96,
        }
        spans = decode_phrase_lattice(
            ["dian", "hua", "yi"],
            "店化一",
            [False, False, False],
            lambda readings: phrases.get(tuple(readings), []),
            lambda _readings, phrase: weights.get(phrase, 0),
            lambda readings, _context: ("化一", False) if readings == ["hua", "yi"] else ("", False),
        )
        self.assertEqual("".join(span.text for span in spans), "電話一")

    def test_personal_phrase_still_wins_when_it_is_the_better_span(self):
        """The guard above must not make learned phrases useless.

        Here the learned phrase covers readings the bundled lexicon has no
        multi-character answer for, so it must still be chosen.
        """
        phrases = {
            ("wang",): ["王", "往"],
            ("xiao",): ["小", "笑"],
            ("ming",): ["明", "名"],
        }
        weights = {"王": 9000, "往": 8000, "小": 20000, "笑": 7000, "明": 30000}
        spans = decode_phrase_lattice(
            ["wang", "xiao", "ming"],
            "往笑名",
            [False, False, False],
            lambda readings: phrases.get(tuple(readings), []),
            lambda _readings, phrase: weights.get(phrase, 0),
            lambda readings, _context: (
                ("王小明", False)
                if readings == ["wang", "xiao", "ming"]
                else ("", False)
            ),
        )
        self.assertEqual("".join(span.text for span in spans), "王小明")
        self.assertTrue(spans[0].personal)


class PersonalContextTests(unittest.TestCase):
    """一個學過的詞不該接管跟它無關的句子。

    實測的病徵：選過一次「程式」之後，「這座城市很美麗」變成「這座程式很美麗」
    ——個人偏好蓋過一個常用 36 倍的詞，而那句話跟程式毫無關係。
    """

    PHRASES = {("cheng", "shi"): ["城市", "程式"]}
    WEIGHTS = {"城市": 38332, "程式": 1059}  # 實際詞庫裡的數字

    def decode(self, personal, contextual):
        return "".join(
            span.text
            for span in decode_phrase_lattice(
                ["cheng", "shi"],
                "？？",
                [False, False],
                lambda readings: self.PHRASES.get(tuple(readings), []),
                lambda _readings, phrase: self.WEIGHTS.get(phrase, 0),
                lambda _readings, _context: (personal, contextual),
            )
        )

    def test_without_context_a_far_more_common_word_keeps_the_span(self) -> None:
        self.assertEqual("城市", self.decode("程式", contextual=False))

    def test_with_matching_context_the_learned_word_wins(self) -> None:
        self.assertEqual("程式", self.decode("程式", contextual=True))

    def test_a_close_preference_still_takes_effect_without_context(self) -> None:
        # 在做(10951)/再做(3057) 只差 3.6 倍。這種真的有歧義的配對，使用者選過
        # 一次就該立刻生效——把門檻訂得太嚴會讓學習整個失去意義。
        phrases = {("zai", "zuo"): ["在做", "再做"]}
        weights = {"在做": 10951, "再做": 3057}
        spans = decode_phrase_lattice(
            ["zai", "zuo"],
            "？？",
            [False, False],
            lambda readings: phrases.get(tuple(readings), []),
            lambda _readings, phrase: weights.get(phrase, 0),
            lambda _readings, _context: ("再做", False),
        )
        self.assertEqual("再做", "".join(span.text for span in spans))

    def test_a_word_the_lexicon_does_not_know_always_wins(self) -> None:
        # 使用者自己的詞彙沒有「內建對手」可以輸給。少了這個豁免，人名之類的
        # 自造詞會因為權重 0 而永遠打不出來。
        self.assertEqual("橙柿", self.decode("橙柿", contextual=False))

    def test_context_is_the_decoded_left_neighbour(self) -> None:
        # 上下文取的是「最佳路徑上左邊那個詞的最後一字」，不是畫面上目前的文字。
        # 那才是這個跨度真正接在後面的字。
        phrases = {("xie",): ["寫"], ("cheng", "shi"): ["城市", "程式"]}
        weights = {"寫": 5000, "城市": 38332, "程式": 1059}
        seen: list[str] = []

        def personal(readings, context):
            if tuple(readings) == ("cheng", "shi"):
                seen.append(context)
                return ("程式", context == "寫")
            return ("", False)

        spans = decode_phrase_lattice(
            ["xie", "cheng", "shi"],
            "？？？",
            [False, False, False],
            lambda readings: phrases.get(tuple(readings), []),
            lambda _readings, phrase: weights.get(phrase, 0),
            personal,
        )

        self.assertIn("寫", seen, f"沒有把左鄰字當成上下文送進來：{seen}")
        self.assertEqual("寫程式", "".join(span.text for span in spans))


if __name__ == "__main__":
    unittest.main()
