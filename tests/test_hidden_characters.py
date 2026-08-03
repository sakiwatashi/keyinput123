"""Hiding candidates must be reversible and must never leave a reading unusable."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from bopomofo_core.hidden_characters import HiddenCharacters


class HiddenCharactersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "hidden-characters.json")

    def _write(self, payload, *, bom: bool = False) -> None:
        encoding = "utf-8-sig" if bom else "utf-8"
        with open(self.path, "w", encoding=encoding) as handle:
            json.dump(payload, handle, ensure_ascii=False)

    def test_nothing_hidden_without_a_list(self) -> None:
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "自", "孳"], store.filter(["字", "自", "孳"]))

    def test_hides_the_listed_characters(self) -> None:
        self._write({"hidden": ["孳", "恣", "磧"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "自"], store.filter(["字", "自", "孳", "恣", "磧"]))

    def test_keeps_multi_character_candidates(self) -> None:
        """The list is per character; phrases must pass through untouched."""
        self._write({"hidden": ["孳"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["孳生"], store.filter(["孳生"]))

    def test_a_fully_hidden_reading_keeps_its_candidates(self) -> None:
        """Hiding every candidate would make the syllable impossible to type."""
        self._write({"hidden": ["ㄅ", "字", "自"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "自"], store.filter(["字", "自"]))

    def test_survives_a_bom(self) -> None:
        """The control panel is PowerShell and may write one; json rejects it."""
        self._write({"hidden": ["孳"]}, bom=True)
        store = HiddenCharacters(self.path)
        self.assertEqual(["字"], store.filter(["字", "孳"]))

    def test_a_broken_list_hides_nothing(self) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "孳"], store.filter(["字", "孳"]))

    def test_frequency_floor_covers_characters_nobody_listed(self) -> None:
        """Hand-picking alone is whack-a-mole: hiding ㄗˋ's 孳 恣 磧 眥 剚 胔
        promoted 胾 扻 倳 牸 芓 絘 from further down the same reading.

        孳 used to disappear here too. It no longer does, and that is
        deliberate: it appears in 孳生, so the lexicon protection keeps it. The
        automation errs towards keeping anything a real word uses, and the
        explicit hidden list is how a user removes what they personally never
        want -- see test_explicit_hide_still_beats_every_protection.
        """
        self._write({"minimum_frequency": 7})
        store = HiddenCharacters(self.path)
        # 胾 appears in no bundled phrase and scores nothing.
        self.assertEqual(["字", "自", "孳"], store.filter(["字", "自", "孳", "胾"]))

    def test_always_show_beats_the_floor(self) -> None:
        """祐 scores 1 and no bundled phrase uses it, so only always_show saves it.

        This is the case the automation cannot get right: 祐 is a common given
        name character that the 1996 written-Chinese survey barely saw and no
        phrase in the index contains. The explicit list exists for exactly this.
        """
        self._write({"minimum_frequency": 7, "always_show": ["祐"]})
        store = HiddenCharacters(self.path)
        self.assertFalse(store.is_hidden("祐"))

        without = HiddenCharacters(self.path)
        self._write({"minimum_frequency": 7})
        without.reload()
        self.assertTrue(without.is_hidden("祐"), "沒有例外時 祐 應該被門檻擋下")

    def test_always_show_beats_an_explicit_hide(self) -> None:
        self._write({"hidden": ["祐"], "always_show": ["祐"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["祐"], store.filter(["祐"]))

    def test_floor_of_zero_is_off(self) -> None:
        self._write({"minimum_frequency": 0})
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "孳"], store.filter(["字", "孳"]))

    def test_set_phrase_characters_survive_the_floor(self) -> None:
        """囫 圇 釜 all score 0, yet 囫圇吞棗 and 破釜沉舟 need them.

        The frequency table is the 1996 「85年常用語詞調查報告」, a survey of
        written Chinese. A character that exists only inside a set phrase
        scores nothing there, so the bundled phrase lexicon is what protects it.
        """
        self._write({"minimum_frequency": 20})
        store = HiddenCharacters(self.path)
        for character in "囫圇釜徇斟竿":
            self.assertFalse(
                store.is_hidden(character),
                f"{character} 出現在內建詞庫，不該被門檻砍掉",
            )

    def test_spoken_particles_survive_the_floor(self) -> None:
        """嗯 scores 7 and 齁 scores 0, and no phrase dictionary lists them."""
        self._write({"minimum_frequency": 50})
        store = HiddenCharacters(self.path)
        for character in "嗯喔啦欸齁嘛耶":
            self.assertFalse(store.is_hidden(character), f"{character} 是常用語氣詞")

    def test_genuinely_obscure_characters_are_still_hidden(self) -> None:
        """The protections must not neuter the feature."""
        self._write({"minimum_frequency": 7})
        store = HiddenCharacters(self.path)
        hidden = [c for c in "眥剚胔襶坔" if store.is_hidden(c)]
        self.assertTrue(hidden, "保護規則把整個功能架空了")

    def test_explicit_hide_still_beats_every_protection(self) -> None:
        self._write({"hidden": ["嗯"], "minimum_frequency": 0})
        store = HiddenCharacters(self.path)
        self.assertTrue(store.is_hidden("嗯"), "明確指定隱藏應優先於保護規則")

    def test_emptying_the_list_brings_characters_back(self) -> None:
        """Hiding is not deleting -- the bundled dictionary is never touched."""
        self._write({"hidden": ["孳"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["字"], store.filter(["字", "孳"]))
        self._write({"hidden": []})
        store.reload()
        self.assertEqual(["字", "孳"], store.filter(["字", "孳"]))


if __name__ == "__main__":
    unittest.main()
