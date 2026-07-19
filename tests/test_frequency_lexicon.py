import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.frequency_lexicon import FrequencyLexicon


class FrequencyLexiconTests(unittest.TestCase):
    def test_bundled_index_is_large_and_contains_common_taiwan_words(self) -> None:
        lexicon = FrequencyLexicon()
        self.assertGreaterEqual(lexicon.entry_count, 100_000)
        self.assertEqual(["優化"], lexicon.candidates([["優"], ["化", "話"]]))
        self.assertEqual(
            ["人工智慧"],
            lexicon.candidates([["人"], ["工"], ["智"], ["慧"]]),
        )
        self.assertEqual(["軟體"], lexicon.candidates([["軟"], ["體"]]))

    def test_filters_by_every_exact_tone_candidate_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phrases.json"
            path.write_text(
                json.dumps(
                    {
                        "meta": {"entry_count": 3},
                        "buckets": {
                            "2": {
                                "優": [
                                    ["優化", 2000],
                                    ["優話", 100],
                                    ["優畫", 50],
                                ]
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            lexicon = FrequencyLexicon(path)

            self.assertEqual(3, lexicon.entry_count)
            self.assertEqual(
                ["優化", "優話"],
                lexicon.candidates([["優", "幽"], ["話", "化"]]),
            )

    def test_missing_or_corrupt_index_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phrases.json"
            self.assertEqual([], FrequencyLexicon(path).candidates([["樹"], ["葉"]]))
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual([], FrequencyLexicon(path).candidates([["樹"], ["葉"]]))
            path.write_text("[]", encoding="utf-8")
            self.assertEqual([], FrequencyLexicon(path).candidates([["樹"], ["葉"]]))


if __name__ == "__main__":
    unittest.main()
