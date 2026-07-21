import unittest

from bopomofo_core.libchewing_provider import (
    COMMON_USAGE_RULES,
    add_literal_bopomofo_candidate,
    apply_common_usage_overrides,
    prioritize_common_character,
)


class CommonUsageTests(unittest.TestCase):
    def test_bu_is_first_for_its_reading(self) -> None:
        self.assertEqual(
            ["不", "部", "步"],
            prioritize_common_character("ㄅㄨˋ", ["部", "步", "不"]),
        )

    def test_zi_defaults_to_character_but_context_can_select_self(self) -> None:
        self.assertEqual(
            ["字", "自", "漬"],
            prioritize_common_character("ㄗˋ", ["自", "漬", "字"]),
        )
        self.assertEqual(
            "自己",
            apply_common_usage_overrides(["ㄗˋ", "ㄐㄧˇ"], "字己"),
        )
        self.assertEqual(
            "自我",
            apply_common_usage_overrides(["ㄗˋ", "ㄨㄛˇ"], "字我"),
        )

    def test_na_defaults_to_demonstrative_not_inside(self) -> None:
        self.assertEqual(
            ["那", "內", "納"],
            prioritize_common_character("ㄋㄚˋ", ["內", "那", "納"]),
        )

    def test_de_defaults_to_possessive_particle(self) -> None:
        self.assertEqual(
            ["的", "得", "地"],
            prioritize_common_character("ㄉㄜ˙", ["得", "地", "的"]),
        )

    def test_complete_reading_exposes_literal_zhuyin_without_replacing_default(self) -> None:
        for reading, literal in (
            ("ㄢˉ", "ㄢ"),
            ("ㄢˊ", "ㄢˊ"),
            ("ㄢˇ", "ㄢˇ"),
            ("ㄢˋ", "ㄢˋ"),
            ("ㄢ˙", "ㄢ˙"),
        ):
            with self.subTest(reading=reading):
                ranked = add_literal_bopomofo_candidate(
                    reading, ["安", "鞍", "庵", "諳"]
                )
                self.assertEqual("安", ranked[0])
                self.assertEqual(literal, ranked[1])

    def test_bu_phrases_are_forced_to_common_usage(self) -> None:
        self.assertEqual(
            "我不要",
            apply_common_usage_overrides(
                ["ㄨㄛˇ", "ㄅㄨˋ", "ㄧㄠˋ"], "我部要"
            ),
        )
        self.assertEqual(
            "不是",
            apply_common_usage_overrides(["ㄅㄨˋ", "ㄕˋ"], "部市"),
        )

    def test_you_hua_prefers_the_common_word_optimize(self) -> None:
        self.assertEqual(
            "優化",
            apply_common_usage_overrides(["ㄧㄡˉ", "ㄏㄨㄚˋ"], "優話"),
        )

    def test_you_xian_ji_prefers_level_not_conjunction(self) -> None:
        self.assertEqual(
            "優先級",
            apply_common_usage_overrides(
                ["ㄧㄡˉ", "ㄒㄧㄢˉ", "ㄐㄧˊ"], "優先及"
            ),
        )

    def test_zai_rules_distinguish_unambiguous_traditional_usage(self) -> None:
        examples = (
            (["ㄗㄞˋ", "ㄐㄧㄢˋ"], "在見", "再見"),
            (["ㄒㄧㄢˋ", "ㄗㄞˋ"], "現再", "現在"),
            (["ㄍㄣˉ", "ㄗㄞˋ"], "跟再", "跟在"),
            (["ㄗㄞˋ", "ㄐㄧㄚˉ"], "再家", "在家"),
            (["ㄗㄞˋ", "ㄧˉ", "ㄘˋ"], "在一刺", "再一次"),
            (["ㄅㄨˋ", "ㄓˉ", "ㄉㄠˋ"], "部之到", "不知道"),
        )
        for readings, engine_result, expected in examples:
            with self.subTest(expected=expected):
                self.assertEqual(
                    expected,
                    apply_common_usage_overrides(readings, engine_result),
                )

    def test_every_common_usage_reading_is_a_completed_syllable(self) -> None:
        tones = frozenset("ˉˊˇˋ˙")
        for pattern, replacement in COMMON_USAGE_RULES:
            with self.subTest(replacement=replacement):
                self.assertTrue(all(reading[-1:] in tones for reading in pattern))

    def test_ambiguous_zai_phrase_is_left_to_the_engine(self) -> None:
        self.assertEqual(
            "在做",
            apply_common_usage_overrides(["ㄗㄞˋ", "ㄗㄨㄛˋ"], "在做"),
        )


if __name__ == "__main__":
    unittest.main()
