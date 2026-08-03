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
        promoted 胾 扻 倳 牸 芓 絘 from further down the same reading."""
        self._write({"minimum_frequency": 7})
        store = HiddenCharacters(self.path)
        # 字 and 自 are common; 孳 is 6 and 胾 is absent from the table.
        self.assertEqual(["字", "自"], store.filter(["字", "自", "孳", "胾"]))

    def test_always_show_beats_the_floor(self) -> None:
        """祐 scores 1, below any floor that removes 恣 at 5."""
        self._write({"minimum_frequency": 7, "always_show": ["祐"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["右", "祐"], store.filter(["右", "祐", "恣"]))

    def test_always_show_beats_an_explicit_hide(self) -> None:
        self._write({"hidden": ["祐"], "always_show": ["祐"]})
        store = HiddenCharacters(self.path)
        self.assertEqual(["祐"], store.filter(["祐"]))

    def test_floor_of_zero_is_off(self) -> None:
        self._write({"minimum_frequency": 0})
        store = HiddenCharacters(self.path)
        self.assertEqual(["字", "孳"], store.filter(["字", "孳"]))

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
