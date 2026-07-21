import unittest

from bopomofo_core.phonetic_corrector import PhoneticCorrector, reading_variants


class PhoneticCorrectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = {
            "ㄧㄣˉ": ["音", "因"],
            "ㄧㄥˉ": ["應", "英"],
            "ㄍㄞˉ": ["該"],
            "ㄍㄢˇ": ["感", "敢"],
        }

        def candidate_lookup(reading: str) -> list[str]:
            return list(self.candidates.get(reading, []))

        def phrase_lookup(columns: list[list[str]]) -> list[str]:
            phrases = ["應該", "音感"]
            return [
                phrase
                for phrase in phrases
                if len(phrase) == len(columns)
                and all(character in column for character, column in zip(phrase, columns))
            ]

        self.candidate_lookup = candidate_lookup
        self.phrase_lookup = phrase_lookup
        self.corrector = PhoneticCorrector()

    def correct(self, readings, text, protected=None):
        return self.corrector.correct(
            readings,
            text,
            protected or [False] * len(text),
            self.candidate_lookup,
            self.phrase_lookup,
        )

    def test_uses_readings_instead_of_enumerating_wrong_characters(self) -> None:
        corrected, changes = self.correct(["ㄧㄣˉ", "ㄍㄞˉ"], "音該")
        self.assertEqual("應該", corrected)
        self.assertTrue(changes[0].used_fuzzy_reading)

        corrected, changes = self.correct(["ㄧㄥˉ", "ㄍㄞˉ"], "英該")
        self.assertEqual("應該", corrected)
        self.assertFalse(changes[0].used_fuzzy_reading)

    def test_preserves_a_valid_phrase_and_explicit_selection(self) -> None:
        self.assertEqual(
            ("音感", []), self.correct(["ㄧㄣˉ", "ㄍㄢˇ"], "音感")
        )
        self.assertEqual(
            ("音該", []),
            self.correct(["ㄧㄣˉ", "ㄍㄞˉ"], "音該", [True, False]),
        )

    def test_common_bopomofo_confusions_are_slot_based(self) -> None:
        self.assertEqual(("ㄧㄣˉ", "ㄧㄥˉ"), reading_variants("ㄧㄣˉ"))
        self.assertEqual(("ㄕˋ", "ㄙˋ"), reading_variants("ㄕˋ"))
        self.assertEqual(("ㄗㄥˉ", "ㄓㄥˉ", "ㄗㄣˉ"), reading_variants("ㄗㄥˉ"))

    def test_live_ranking_can_disable_fuzzy_pronunciation_changes(self) -> None:
        corrected, changes = self.corrector.correct(
            ["ㄧㄣˉ", "ㄍㄞˉ"],
            "音該",
            [False, False],
            self.candidate_lookup,
            self.phrase_lookup,
            allow_fuzzy=False,
        )
        self.assertEqual(("音該", []), (corrected, changes))

    def test_long_valid_word_blocks_shorter_overlapping_rewrite(self) -> None:
        columns = {
            "寫": ["寫"],
            "程": ["程", "成"],
            "式": ["式"],
        }

        def phrase_lookup(candidate_columns):
            if len(candidate_columns) == 2 and "寫" in candidate_columns[0]:
                return ["寫成"]
            return []

        corrected, changes = self.corrector.correct(
            ["寫", "程", "式"],
            "寫程式",
            [False, False, False],
            lambda reading: columns[reading],
            phrase_lookup,
            phrase_validator=lambda phrase: phrase == "寫程式",
            allow_fuzzy=False,
        )
        self.assertEqual(("寫程式", []), (corrected, changes))

    def test_rejects_misaligned_state(self) -> None:
        with self.assertRaises(ValueError):
            self.corrector.correct(
                ["ㄧㄣˉ"],
                "音該",
                [False, False],
                self.candidate_lookup,
                self.phrase_lookup,
            )


if __name__ == "__main__":
    unittest.main()
