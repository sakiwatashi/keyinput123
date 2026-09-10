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

        def known_phrase_lookup(readings: list[str]) -> list[str]:
            known = {
                ("ㄧㄥˉ", "ㄍㄞˉ"): ["應該"],
                ("ㄧㄣˉ", "ㄍㄢˇ"): ["音感"],
            }
            return known.get(tuple(readings), [])

        self.candidate_lookup = candidate_lookup
        self.phrase_lookup = phrase_lookup
        self.known_phrase_lookup = known_phrase_lookup
        self.corrector = PhoneticCorrector()

    def correct(self, readings, text, protected=None):
        return self.corrector.correct(
            readings,
            text,
            protected or [False] * len(text),
            self.candidate_lookup,
            self.phrase_lookup,
            self.known_phrase_lookup,
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

    def test_text_only_word_cannot_borrow_an_unrelated_pronunciation(self) -> None:
        def candidate_lookup(reading: str) -> list[str]:
            return {
                "ㄅㄟˋ": ["被", "貝"],
                "ㄑㄩㄝˋ": ["卻", "殼"],
                "ㄎㄜˊ": ["殼"],
            }.get(reading, [])

        def phrase_lookup(columns: list[list[str]]) -> list[str]:
            return [
                phrase
                for phrase in ["貝殼"]
                if all(character in column for character, column in zip(phrase, columns))
            ]

        def known_phrase_lookup(readings: list[str]) -> list[str]:
            return {
                ("ㄅㄟˋ", "ㄑㄩㄝˋ"): ["被卻"],
                ("ㄅㄟˋ", "ㄎㄜˊ"): ["貝殼"],
            }.get(tuple(readings), [])

        wrong = self.corrector.correct(
            ["ㄅㄟˋ", "ㄑㄩㄝˋ"],
            "貝卻",
            [False, False],
            candidate_lookup,
            phrase_lookup,
            known_phrase_lookup,
            allow_fuzzy=False,
        )
        correct = self.corrector.correct(
            ["ㄅㄟˋ", "ㄎㄜˊ"],
            "被殼",
            [False, False],
            candidate_lookup,
            phrase_lookup,
            known_phrase_lookup,
            allow_fuzzy=False,
        )
        self.assertEqual(("貝卻", []), wrong)
        self.assertEqual("貝殼", correct[0])
        self.assertFalse(correct[1][0].used_fuzzy_reading)

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


class FuzzyEvidenceTests(unittest.TestCase):
    """模糊路徑的證據要比精確路徑嚴。

    打「六扇門」出來是「六三門」。ㄕㄢˋ 被換成 ㄙㄢˋ（ㄕ／ㄙ 混淆）之後，
    寬鬆的證據來源不管聲調照樣回「三門」（真正讀音是 ㄙㄢˉ），於是一個猜出來
    的讀音配上一個猜出來的詞就被放行了。三根本不是使用者打的那個音。
    """

    def setUp(self) -> None:
        self.corrector = PhoneticCorrector()
        self.columns = {"ㄕㄢˋ": ["善", "扇", "三"], "ㄇㄣˊ": ["門"]}

        def candidate_lookup(reading: str) -> list[str]:
            return list(self.columns.get(reading, []))

        def phrase_lookup(columns: list[list[str]]) -> list[str]:
            phrases = ["三門"]
            return [
                phrase
                for phrase in phrases
                if len(phrase) == len(columns)
                and all(c in column for c, column in zip(phrase, columns))
            ]

        self.candidate_lookup = candidate_lookup
        self.phrase_lookup = phrase_lookup

    @staticmethod
    def loose(readings: list[str]) -> list[str]:
        # 不管聲調的來源：問它 ㄙㄢˋ ㄇㄣˊ 也回「三門」。
        if readings[0].startswith("ㄙㄢ"):
            return ["三門"]
        return []

    @staticmethod
    def strict(readings: list[str]) -> list[str]:
        # 以讀音為準：三門 只在 ㄙㄢˉ ㄇㄣˊ 底下。
        if readings == ["ㄙㄢˉ", "ㄇㄣˊ"]:
            return ["三門"]
        return []

    def correct(self, fuzzy_lookup):
        return self.corrector.correct(
            ["ㄕㄢˋ", "ㄇㄣˊ"],
            "善門",
            [False, False],
            self.candidate_lookup,
            self.phrase_lookup,
            known_phrase_lookup=self.loose,
            replacement_phrase_lookup=self.loose,
            fuzzy_evidence_lookup=fuzzy_lookup,
        )

    def test_a_loose_source_lets_the_wrong_sound_through(self) -> None:
        # 這一條記錄的是壞掉時的樣子。沒有它，下一條看不出在守什麼。
        text, changes = self.correct(None)
        self.assertEqual("三門", text)
        self.assertTrue(changes[0].used_fuzzy_reading)

    def test_reading_authoritative_evidence_refuses_it(self) -> None:
        text, changes = self.correct(self.strict)
        self.assertEqual("善門", text)
        self.assertEqual([], changes)

    def test_a_genuine_confusion_is_still_corrected(self) -> None:
        # 收緊不能把模糊修正整個關掉：讀音真的差一格、而且那個讀音下確實有詞
        # 的時候照樣要修。
        def strict_at_the_typed_tone(readings: list[str]) -> list[str]:
            return ["三門"] if readings == ["ㄙㄢˋ", "ㄇㄣˊ"] else []

        text, changes = self.correct(strict_at_the_typed_tone)
        self.assertEqual("三門", text)
        self.assertTrue(changes[0].used_fuzzy_reading)
