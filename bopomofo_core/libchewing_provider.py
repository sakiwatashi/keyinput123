"""libchewing Simple Engine candidate provider.

The `chewing_module` argument makes the provider testable and allows the PIME
package to use its private 32-bit DLL without replacing PIME's stock engine.
"""

from __future__ import annotations

from types import ModuleType

from .frequency_lexicon import FrequencyLexicon
from .keymap import keys_for_reading
from .reading_phrase_lexicon import ReadingPhraseLexicon
from .taiwan_frequency import TaiwanFrequency
from .hidden_characters import shared_hidden_characters as HIDDEN_CHARACTERS


SIMPLE_CONVERSION_ENGINE = 0
PHRASE_CONVERSION_ENGINE = 1
CHINESE_MODE = 1
# Keep a practical long tail for explicit expansion, but stop before the
# dictionary's rare-character tail becomes noise.
MAX_CANDIDATES = 20
MAX_CONTEXT_SYLLABLES = 64
FREQUENCY_LEXICON = FrequencyLexicon()
TAIWAN_FREQUENCY = TaiwanFrequency()
READING_PHRASE_LEXICON = ReadingPhraseLexicon()

# Conservative Traditional Chinese usage rules. Only unambiguous phrases
# belong here; ambiguous pairs such as 在做/再做 remain the phrase engine's job.
COMMON_USAGE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # Longer spans first so exact_common_usage_phrase and left-to-right
    # overrides prefer complete multi-syllable words over shorter suffixes.
    (("ㄧㄡˉ", "ㄒㄧㄢˉ", "ㄐㄧˊ"), "優先級"),
    (("ㄐㄧㄡˋ", "ㄎㄜˇ", "ㄧˇ"), "就可以"),
    (("ㄍㄨㄥˉ", "ㄋㄥˊ", "ㄐㄧㄢˋ"), "功能鍵"),
    (("ㄎㄨㄥˋ", "ㄅㄞˊ", "ㄐㄧㄢˋ"), "空白鍵"),
    (("ㄕˋ", "ㄐㄧㄝˋ", "ㄍㄨㄢˉ"), "世界觀"),
    (("ㄨㄛˇ", "ㄅㄨˋ", "ㄧㄠˋ"), "我不要"),
    (("ㄅㄨˋ", "ㄓˉ", "ㄉㄠˋ"), "不知道"),
    (("ㄗㄞˋ", "ㄧˉ", "ㄘˋ"), "再一次"),
    (("ㄧㄡˉ", "ㄒㄧㄢˉ"), "優先"),
    (("ㄧㄡˉ", "ㄏㄨㄚˋ"), "優化"),
    (("ㄎㄜˇ", "ㄧˇ"), "可以"),
    (("ㄐㄧㄡˋ", "ㄕˋ"), "就是"),
    (("ㄨㄣˋ", "ㄊㄧˊ"), "問題"),
    (("ㄧㄣˉ", "ㄨㄟˋ"), "因為"),
    (("ㄏㄡˋ", "ㄒㄩㄢˇ"), "候選"),
    (("ㄍㄨㄟˉ", "ㄗㄜˊ"), "規則"),
    (("ㄒㄩㄢˇ", "ㄗㄜˊ"), "選擇"),
    (("ㄕㄜˋ", "ㄐㄧˋ"), "設計"),
    (("ㄕˊ", "ㄒㄧㄢˋ"), "實現"),
    (("ㄨㄟˊ", "ㄒㄧㄡˉ"), "維修"),
    (("ㄅㄨˋ", "ㄊㄞˋ"), "不太"),
    (("ㄐㄧㄡˉ", "ㄘㄨㄛˋ"), "糾錯"),
    (("ㄓㄨˋ", "ㄧㄣˉ"), "注音"),
    (("ㄉㄧˋ", "ㄊㄨˊ"), "地圖"),
    (("ㄌㄨˋ", "ㄒㄧㄢˋ"), "路線"),
    (("ㄗㄨㄥˋ", "ㄒㄧㄤˋ"), "縱向"),
    # Do not force ㄧㄡˋㄐㄧㄢˋ→右鍵: 又見 is a valid exact-reading phrase.
    (("ㄗˋ", "ㄐㄧˇ"), "自己"),
    (("ㄗˋ", "ㄨㄛˇ"), "自我"),
    (("ㄅㄨˋ", "ㄧㄠˋ"), "不要"),
    (("ㄅㄨˋ", "ㄕˋ"), "不是"),
    (("ㄅㄨˋ", "ㄏㄨㄟˋ"), "不會"),
    (("ㄅㄨˋ", "ㄋㄥˊ"), "不能"),
    (("ㄅㄨˋ", "ㄩㄥˋ"), "不用"),
    (("ㄅㄨˋ", "ㄒㄧㄤˇ"), "不想"),
    (("ㄗㄞˋ", "ㄐㄧㄢˋ"), "再見"),
    (("ㄗㄞˋ", "ㄧㄝˇ"), "再也"),
    (("ㄗㄞˋ", "ㄌㄞˊ"), "再來"),
    (("ㄒㄧㄢˋ", "ㄗㄞˋ"), "現在"),
    (("ㄙㄨㄛˇ", "ㄗㄞˋ"), "所在"),
    (("ㄍㄣˉ", "ㄗㄞˋ"), "跟在"),
    (("ㄓㄥˋ", "ㄗㄞˋ"), "正在"),
    (("ㄗㄞˋ", "ㄐㄧㄚˉ"), "在家"),
    (("ㄗㄞˋ", "ㄓㄜˋ"), "在這"),
    (("ㄗㄞˋ", "ㄋㄚˋ"), "在那"),
    (("ㄗㄞˋ", "ㄋㄚˇ"), "在哪"),
)


def prioritize_common_character(reading: str, candidates: list[str]) -> list[str]:
    """Put a small set of overwhelmingly common characters first."""
    # These defaults only control an isolated syllable. Contextual word rules
    # below may still turn ㄗˋ into 自 in words such as 自己 and 自我.
    preferred = {
        "ㄅㄨˋ": "不",
        "ㄉㄜ˙": "的",
        "ㄋㄚˋ": "那",
        "ㄕˋ": "是",
        "ㄗˋ": "字",
        "ㄗㄨㄛˋ": "做",
    }.get(reading)
    if preferred is None or preferred not in candidates:
        return candidates
    return [preferred] + [candidate for candidate in candidates if candidate != preferred]


def add_literal_bopomofo_candidate(
    reading: str, candidates: list[str]
) -> list[str]:
    """Expose the typed Zhuyin itself near the front of complete readings.

    Microsoft Bopomofo offers the literal phonetic spelling as a candidate.
    First tone is conventionally unmarked in displayed Zhuyin. Keeping this at
    position two preserves the normal Chinese default while keeping the
    phonetic spelling visible in a compact Microsoft-style five-item page.
    """
    if not reading:
        return candidates
    literal = reading[:-1] if reading.endswith("ˉ") else reading
    if literal in candidates:
        current_index = candidates.index(literal)
        if current_index <= 1:
            return candidates
        # Some dictionary rows already contain the raw spelling deep in the
        # tail. Presence alone is not enough: the UI contract requires it in
        # the first four, so normalize an existing literal to position two.
        without_literal = [
            candidate for candidate in candidates if candidate != literal
        ]
        return without_literal[:1] + [literal] + without_literal[1:]
    insert_at = min(1, len(candidates))
    return candidates[:insert_at] + [literal] + candidates[insert_at:]


def apply_common_usage_overrides(readings: list[str], phrase: str) -> str:
    """Correct unambiguous high-frequency phrases in an engine result."""
    if len(readings) != len(phrase):
        return phrase
    result = list(phrase)
    for pattern, replacement in COMMON_USAGE_RULES:
        width = len(pattern)
        for start in range(len(readings) - width + 1):
            if tuple(readings[start : start + width]) == pattern:
                result[start : start + width] = replacement
    return "".join(result)


def exact_common_usage_phrase(readings: list[str]) -> str:
    key = tuple(readings)
    for pattern, replacement in COMMON_USAGE_RULES:
        if key == pattern:
            return replacement
    return ""


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
        self._trusted_phrase_cache: dict[tuple[str, ...], list[str]] = {}

    def candidates(self, reading: str) -> list[str]:
        self.context.Reset()
        for key in keys_for_reading(reading):
            self.context.handle_Default(ord(key))

        total = self.context.cand_TotalChoice()
        if total <= 0:
            return add_literal_bopomofo_candidate(reading, [])
        self.context.cand_Enumerate()
        results: list[str] = []
        limit = min(total, MAX_CANDIDATES)
        while self.context.cand_hasNext() and len(results) < limit:
            results.append(self.context.cand_String().decode("utf-8"))
        # Dictionary order is reading-aware; global character frequency is
        # not. Preserve the exact-reading default so a common alternate
        # pronunciation cannot promote 員 over 運 for ㄩㄣˋ, then use Taiwan
        # frequency to organize the remaining candidates.
        results = TAIWAN_FREQUENCY.rank_characters(results, preserve_first=True)
        # Applied after ranking and before the literal Zhuyin is added, so a
        # hidden character cannot occupy a slot and the raw Zhuyin escape
        # always survives.
        results = HIDDEN_CHARACTERS.filter(results)
        results = prioritize_common_character(reading, results)
        return add_literal_bopomofo_candidate(reading, results)[:MAX_CANDIDATES]

    @staticmethod
    def lexical_phrase_candidates(readings: list[str]) -> list[str]:
        """Return bundled phrases with explicit complete-reading evidence."""
        common = exact_common_usage_phrase(readings)
        return list(
            dict.fromkeys(
                ([common] if common else [])
                + READING_PHRASE_LEXICON.candidates(readings, MAX_CANDIDATES)
            )
        )[:MAX_CANDIDATES]

    def trusted_phrase_candidates(self, readings: list[str]) -> list[str]:
        """Return exact-reading words, plus a conservative engine fallback.

        The bundled reading lexicon is authoritative. Some ordinary words are
        nevertheless absent from its source data; for those spans, accept
        libchewing's exact-reading best phrase only when the independent
        Traditional Chinese frequency index also recognises the result.
        """
        key = tuple(readings)
        cached = self._trusted_phrase_cache.get(key)
        if cached is not None:
            return list(cached)

        results = self.lexical_phrase_candidates(readings)
        if not results:
            best = self.best_phrase(readings)
            if best and self.is_frequent_phrase(best):
                results = [best]
        self._trusted_phrase_cache[key] = list(results)
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
        if len(phrase) != len(readings):
            return ""
        return apply_common_usage_overrides(readings, phrase)

    def dictionary_phrase_candidates(self, readings: list[str]) -> list[str]:
        """Return exact-span phrases explicitly exposed by libchewing."""
        if len(readings) < 2 or len(readings) > MAX_CONTEXT_SYLLABLES:
            return []
        curated = self.lexical_phrase_candidates(readings)
        self.phrase_context.Reset()
        for reading in readings:
            for key in keys_for_reading(reading):
                self.phrase_context.handle_Default(ord(key))

        # libchewing exposes phrase candidates at the beginning of their
        # reading span.  Input leaves the cursor at the end, so move it home.
        for _ in readings:
            self.phrase_context.handle_Left()
        self.phrase_context.handle_Down()

        total = self.phrase_context.cand_TotalChoice()
        results: list[str] = list(curated)
        if total > 0:
            self.phrase_context.cand_Enumerate()
            while (
                self.phrase_context.cand_hasNext()
                and len(results) < MAX_CANDIDATES
            ):
                candidate = self.phrase_context.cand_String().decode("utf-8")
                if len(candidate) != len(readings):
                    continue
                candidate = apply_common_usage_overrides(readings, candidate)
                if candidate not in results:
                    results.append(candidate)

        return results[:MAX_CANDIDATES]

    def phrase_candidates(self, readings: list[str]) -> list[str]:
        """Return curated whole-phrase candidates for one exact reading span."""
        results = self.dictionary_phrase_candidates(readings)

        best = self.best_phrase(readings)
        if best:
            results = [best] + [candidate for candidate in results if candidate != best]
        return results[:MAX_CANDIDATES]

    @staticmethod
    def phrase_weight(readings: list[str], phrase: str) -> int:
        return READING_PHRASE_LEXICON.weight(readings, phrase)

    def frequent_phrase_candidates(
        self, candidate_columns: list[list[str]]
    ) -> list[str]:
        taiwan = TAIWAN_FREQUENCY.phrase_candidates(
            candidate_columns, limit=MAX_CANDIDATES
        )
        expanded = FREQUENCY_LEXICON.candidates(
            candidate_columns, limit=MAX_CANDIDATES
        )
        return list(dict.fromkeys(taiwan + expanded))[:MAX_CANDIDATES]

    @staticmethod
    def is_frequent_phrase(phrase: str) -> bool:
        """Recognize valid bundled words even outside the top-20 result tail."""
        return TAIWAN_FREQUENCY.contains_phrase(phrase) or FREQUENCY_LEXICON.contains(
            phrase
        )
