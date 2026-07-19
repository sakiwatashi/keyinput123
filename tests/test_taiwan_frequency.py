import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.taiwan_frequency import TaiwanFrequency


class TaiwanFrequencyTests(unittest.TestCase):
    def test_bundled_official_index_is_present(self) -> None:
        frequency = TaiwanFrequency()
        self.assertGreaterEqual(frequency.character_count, 4_000)
        self.assertGreaterEqual(frequency.phrase_count, 40_000)
        self.assertEqual(
            ["優化"], frequency.phrase_candidates([["優"], ["話", "化"]])
        )
        self.assertEqual(
            ["軟體"], frequency.phrase_candidates([["軟"], ["體", "件"]])
        )

    def test_character_ranking_uses_frequency_and_preserves_unknown_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "taiwan.json"
            path.write_text(
                json.dumps(
                    {
                        "meta": {"character_count": 2, "phrase_count": 0},
                        "characters": {"字": 100, "自": 50},
                        "buckets": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            frequency = TaiwanFrequency(path)
            self.assertEqual(
                ["字", "自", "甲", "乙"],
                frequency.rank_characters(["自", "甲", "字", "乙"]),
            )

    def test_missing_index_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            frequency = TaiwanFrequency(Path(temp_dir) / "missing.json")
            self.assertEqual(
                ["甲", "乙"], frequency.rank_characters(["甲", "乙"])
            )
            self.assertEqual([], frequency.phrase_candidates([["甲"], ["乙"]]))


if __name__ == "__main__":
    unittest.main()
