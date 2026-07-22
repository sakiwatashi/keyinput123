"""Reading-aware phrase correction for an uncommitted Bopomofo buffer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence


CandidateLookup = Callable[[str], List[str]]
PhraseLookup = Callable[[List[List[str]]], List[str]]
KnownPhraseLookup = Callable[[List[str]], List[str]]
PhraseValidator = Callable[[str], bool]

_INITIAL_CONFUSIONS = {
    "ㄓ": "ㄗ",
    "ㄗ": "ㄓ",
    "ㄔ": "ㄘ",
    "ㄘ": "ㄔ",
    "ㄕ": "ㄙ",
    "ㄙ": "ㄕ",
}
_RIME_CONFUSIONS = {"ㄣ": "ㄥ", "ㄥ": "ㄣ"}
_TONES = frozenset("ˉˊˇˋ˙")


def reading_variants(reading: str) -> tuple[str, ...]:
    """Return conservative Taiwanese Bopomofo confusions for one syllable.

    The original reading is always first. Variants change one phonetic slot at
    a time, so the language model—not a list of wrong output characters—decides
    whether a common word exists for the nearby pronunciation.
    """
    if not reading:
        return ()
    tone = reading[-1] if reading[-1] in _TONES else ""
    body = reading[:-1] if tone else reading
    variants = [reading]

    if body[:1] in _INITIAL_CONFUSIONS:
        variants.append(_INITIAL_CONFUSIONS[body[0]] + body[1:] + tone)
    if body[-1:] in _RIME_CONFUSIONS:
        variants.append(body[:-1] + _RIME_CONFUSIONS[body[-1]] + tone)
    return tuple(dict.fromkeys(variants))


@dataclass(frozen=True)
class PhoneticCorrection:
    start: int
    original: str
    corrected: str
    used_fuzzy_reading: bool


class PhoneticCorrector:
    """Re-decode words from readings and the bundled phrase indexes."""

    def __init__(self, max_phrase_length: int = 12) -> None:
        self.max_phrase_length = max(2, max_phrase_length)

    @staticmethod
    def _single_character_candidates(
        current: str, readings: Sequence[str], candidate_lookup: CandidateLookup
    ) -> tuple[list[str], list[str]]:
        exact = [current]
        for candidate in candidate_lookup(readings[0]):
            if len(candidate) == 1 and candidate not in exact:
                exact.append(candidate)

        expanded = list(exact)
        for variant in readings[1:]:
            for candidate in candidate_lookup(variant):
                if len(candidate) == 1 and candidate not in expanded:
                    expanded.append(candidate)
        return exact, expanded

    def correct(
        self,
        readings: Sequence[str],
        text: str,
        protected: Sequence[bool],
        candidate_lookup: CandidateLookup,
        phrase_lookup: PhraseLookup,
        known_phrase_lookup: KnownPhraseLookup | None = None,
        phrase_validator: PhraseValidator | None = None,
        allow_fuzzy: bool = True,
        replacement_phrase_lookup: KnownPhraseLookup | None = None,
    ) -> tuple[str, list[PhoneticCorrection]]:
        if len(readings) != len(text) or len(protected) != len(text):
            raise ValueError("readings, text, and protection mask must align")
        if len(text) < 2:
            return text, []

        exact_columns: list[list[str]] = []
        expanded_columns: list[list[str]] = []
        for current, reading in zip(text, readings):
            variants = reading_variants(reading)
            if not variants:
                exact_columns.append([current])
                expanded_columns.append([current])
                continue
            exact, expanded = self._single_character_candidates(
                current, variants, candidate_lookup
            )
            exact_columns.append(exact)
            expanded_columns.append(expanded if allow_fuzzy else exact)

        characters = list(text)
        changes: list[PhoneticCorrection] = []
        start = 0
        while start < len(characters) - 1:
            remaining = len(characters) - start
            matched = False
            for width in range(min(self.max_phrase_length, remaining), 1, -1):
                end = start + width
                if any(protected[start:end]):
                    continue
                current = "".join(characters[start:end])

                if phrase_validator is not None and phrase_validator(current):
                    start = end
                    matched = True
                    break
                if known_phrase_lookup is not None and current in known_phrase_lookup(
                    list(readings[start:end])
                ):
                    start = end
                    matched = True
                    break

                span_readings = list(readings[start:end])
                exact_phrases = phrase_lookup(exact_columns[start:end])
                evidence_lookup = (
                    replacement_phrase_lookup or known_phrase_lookup
                )
                if evidence_lookup is not None:
                    known_exact = set(evidence_lookup(span_readings))
                    exact_phrases = [
                        phrase for phrase in exact_phrases if phrase in known_exact
                    ]
                # A known phrase matching the user's current text is valid,
                # even if another phrase has a higher raw corpus frequency.
                if current in exact_phrases:
                    start = end
                    matched = True
                    break
                if exact_phrases:
                    replacement = exact_phrases[0]
                    fuzzy = False
                elif allow_fuzzy:
                    fuzzy_phrases = phrase_lookup(expanded_columns[start:end])
                    if evidence_lookup is not None:
                        # Fuzzy correction is deliberately limited to one
                        # changed phonetic slot. Validate every proposed word
                        # against the exact phrase engine for that nearby
                        # reading, rather than trusting text-only corpus data.
                        known_fuzzy: set[str] = set()
                        for offset, reading in enumerate(span_readings):
                            for variant in reading_variants(reading)[1:]:
                                variant_readings = list(span_readings)
                                variant_readings[offset] = variant
                                known_fuzzy.update(
                                    evidence_lookup(variant_readings)
                                )
                        fuzzy_phrases = [
                            phrase
                            for phrase in fuzzy_phrases
                            if phrase in known_fuzzy
                        ]
                    if not fuzzy_phrases:
                        continue
                    replacement = fuzzy_phrases[0]
                    fuzzy = True
                else:
                    continue

                if len(replacement) != width or replacement == current:
                    continue
                characters[start:end] = replacement
                changes.append(
                    PhoneticCorrection(start, current, replacement, fuzzy)
                )
                start = end
                matched = True
                break
            if not matched:
                start += 1
        return "".join(characters), changes
