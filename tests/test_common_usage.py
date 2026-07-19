import unittest

from bopomofo_core.libchewing_provider import (
    apply_common_usage_overrides,
    prioritize_common_character,
)


class CommonUsageTests(unittest.TestCase):
    def test_bu_is_first_for_its_reading(self) -> None:
        self.assertEqual(
            ["不", "部", "步"],
            prioritize_common_character("ㄅㄨˋ", ["部", "步", "不"]),
        )

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

    def test_zai_rules_distinguish_unambiguous_traditional_usage(self) -> None:
        examples = (
            (["ㄗㄞˋ", "ㄐㄧㄢˋ"], "在見", "再見"),
            (["ㄒㄧㄢˋ", "ㄗㄞˋ"], "現再", "現在"),
            (["ㄍㄣ", "ㄗㄞˋ"], "跟再", "跟在"),
            (["ㄗㄞˋ", "ㄐㄧㄚ"], "再家", "在家"),
        )
        for readings, engine_result, expected in examples:
            with self.subTest(expected=expected):
                self.assertEqual(
                    expected,
                    apply_common_usage_overrides(readings, engine_result),
                )

    def test_ambiguous_zai_phrase_is_left_to_the_engine(self) -> None:
        self.assertEqual(
            "在做",
            apply_common_usage_overrides(["ㄗㄞˋ", "ㄗㄨㄛˋ"], "在做"),
        )


if __name__ == "__main__":
    unittest.main()
