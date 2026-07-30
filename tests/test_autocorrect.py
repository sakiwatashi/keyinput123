import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.autocorrect import Autocorrector


class AutocorrectTests(unittest.TestCase):
    def test_bundled_rules_correct_high_confidence_typos(self) -> None:
        autocorrector = Autocorrector()
        self.assertGreaterEqual(autocorrector.rule_count, 60)
        self.assertTrue(
            {"因該", "音該", "英該"}.isdisjoint(
                rule.wrong for rule in autocorrector.rules
            )
        )
        corrected, changes = autocorrector.correct("我以經迫不急待了")
        self.assertEqual("我已經迫不及待了", corrected)
        self.assertEqual(
            ["以經", "迫不急待"],
            [c.wrong for c in changes],
        )
        # Feedback-reviewed everyday tech typos must correct live without
        # waiting for the candidate menu.
        feedback_cases = (
            ("這個問提舊是可已設記", "這個問題就是可以設計"),
            ("空白劍跟功能見", "空白鍵跟功能鍵"),
            ("優先註音", "優先注音"),
            ("舊可已後選", "就可以候選"),
        )
        for wrong, expected in feedback_cases:
            with self.subTest(wrong=wrong):
                fixed, _ = autocorrector.correct(wrong)
                self.assertEqual(expected, fixed)

    def test_explicitly_selected_character_protects_the_whole_rule_span(self) -> None:
        autocorrector = Autocorrector()
        corrected, changes = autocorrector.correct("以經", [True, False])
        self.assertEqual("以經", corrected)
        self.assertEqual([], changes)

    def test_does_not_force_context_dependent_or_valid_variants(self) -> None:
        autocorrector = Autocorrector()
        text = "他的作法布置得很好而且我在這裡"
        self.assertEqual((text, []), autocorrector.correct(text))

    def test_longest_rule_wins_and_rules_do_not_cascade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.json"
            path.write_text(
                json.dumps(
                    {
                        "meta": {"sources": [{"id": "test"}]},
                        "rules": [
                            {"wrong": "甲乙", "correct": "乙丙", "source": "test"},
                            {"wrong": "甲乙丙", "correct": "丙乙甲", "source": "test"},
                            {"wrong": "乙丙", "correct": "丁戊", "source": "test"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            corrected, changes = Autocorrector(path).correct("甲乙丙")
            self.assertEqual("丙乙甲", corrected)
            self.assertEqual(["甲乙丙"], [change.wrong for change in changes])

    def test_missing_corrupt_or_invalid_rules_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.json"
            self.assertEqual(("以經", []), Autocorrector(path).correct("以經"))
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(0, Autocorrector(path).rule_count)
            path.write_text(
                json.dumps(
                    {
                        "meta": {"sources": [{"id": "test"}]},
                        "rules": [
                            {"wrong": "長短", "correct": "不等長", "source": "test"},
                            {"wrong": "未知", "correct": "來源", "source": "missing"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual(0, Autocorrector(path).rule_count)

    def test_rejects_a_mismatched_protection_mask(self) -> None:
        with self.assertRaises(ValueError):
            Autocorrector().correct("以經", [False])


if __name__ == "__main__":
    unittest.main()
