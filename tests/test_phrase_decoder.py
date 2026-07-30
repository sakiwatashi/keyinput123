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
            lambda _readings: "",
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
            lambda readings: "",
        )
        self.assertEqual("".join(span.text for span in spans), "層數較高")

    def test_explicit_selection_is_a_hard_boundary(self):
        spans = decode_phrase_lattice(
            ["r0", "r1", "r2", "r3"],
            "曾恕叫高",
            [True, False, False, False],
            self.lookup,
            self.weight,
            lambda readings: "",
        )
        self.assertEqual("".join(span.text for span in spans), "曾恕較高")

    def test_personal_phrase_beats_a_bundled_phrase(self):
        spans = decode_phrase_lattice(
            ["r0", "r1"],
            "曾恕",
            [False, False],
            self.lookup,
            self.weight,
            lambda readings: "自訂" if readings == ["r0", "r1"] else "",
        )
        self.assertEqual("".join(span.text for span in spans), "自訂")
        self.assertTrue(spans[0].personal)


if __name__ == "__main__":
    unittest.main()
