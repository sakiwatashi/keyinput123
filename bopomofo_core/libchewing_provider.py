"""libchewing Simple Engine candidate provider.

The `chewing_module` argument makes the provider testable and allows the PIME
package to use its private 32-bit DLL without replacing PIME's stock engine.
"""

from __future__ import annotations

from types import ModuleType

from .keymap import keys_for_reading


SIMPLE_CONVERSION_ENGINE = 0
PHRASE_CONVERSION_ENGINE = 1
CHINESE_MODE = 1
MAX_CANDIDATES = 5
MAX_CONTEXT_SYLLABLES = 64


class LibChewingProvider:
    def __init__(self, chewing_module: ModuleType) -> None:
        self.module = chewing_module
        self.context = chewing_module.ChewingContext(
            syspath=chewing_module.CHEWING_DATA_DIR.encode("utf-8"),
            userpath=None,
        )
        self.context.set_ChiEngMode(CHINESE_MODE)
        result = self.context.config_set_int(
            b"chewing.conversion_engine", SIMPLE_CONVERSION_ENGINE
        )
        if result != 0:
            raise RuntimeError("libchewing 無法切換到 Simple Engine")
        self.context.config_set_int(b"chewing.candidates_per_page", MAX_CANDIDATES)
        # The dictionary's curated order is more natural for Traditional
        # Chinese than libchewing's optional raw frequency sort.
        self.context.config_set_int(b"chewing.sort_candidates_by_frequency", 0)

        # A second context uses libchewing's full phrase converter.  It never
        # controls the UI or segmentation; it is only a background ranking
        # oracle for the editable per-character composition.
        self.phrase_context = chewing_module.ChewingContext(
            syspath=chewing_module.CHEWING_DATA_DIR.encode("utf-8"),
            userpath=None,
        )
        self.phrase_context.set_ChiEngMode(CHINESE_MODE)
        result = self.phrase_context.config_set_int(
            b"chewing.conversion_engine", PHRASE_CONVERSION_ENGINE
        )
        if result != 0:
            raise RuntimeError("libchewing 無法啟用詞彙索引引擎")
        self.phrase_context.set_maxChiSymbolLen(MAX_CONTEXT_SYLLABLES)

    def candidates(self, reading: str) -> list[str]:
        self.context.Reset()
        for key in keys_for_reading(reading):
            self.context.handle_Default(ord(key))

        total = self.context.cand_TotalChoice()
        if total <= 0:
            return []
        self.context.cand_Enumerate()
        results: list[str] = []
        limit = min(total, MAX_CANDIDATES)
        while self.context.cand_hasNext() and len(results) < limit:
            results.append(self.context.cand_String().decode("utf-8"))
        return results

    def best_phrase(self, readings: list[str]) -> str:
        """Return the phrase dictionary's best text for complete readings."""
        if not readings:
            return ""
        readings = readings[-MAX_CONTEXT_SYLLABLES:]
        self.phrase_context.Reset()
        for reading in readings:
            for key in keys_for_reading(reading):
                self.phrase_context.handle_Default(ord(key))
        value = self.phrase_context.buffer_String()
        if not value:
            return ""
        phrase = value.decode("utf-8")
        return phrase if len(phrase) == len(readings) else ""
