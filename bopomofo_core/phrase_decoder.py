"""Dynamic-programming decoder for an editable Bopomofo sentence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Sequence


PhraseLookup = Callable[[List[str]], List[str]]
PhraseWeight = Callable[[List[str], str], int]
PersonalLookup = Callable[[List[str]], str]


@dataclass(frozen=True)
class DecodedSpan:
    start: int
    end: int
    text: str
    personal: bool = False


@dataclass(frozen=True)
class _Path:
    personal_characters: int
    lexical_characters: int
    compaction: int
    frequency_score: float
    spans: tuple[DecodedSpan, ...]

    @property
    def score(self) -> tuple[int, int, int, float]:
        return (
            self.personal_characters,
            self.lexical_characters,
            self.compaction,
            self.frequency_score,
        )


def decode_phrase_lattice(
    readings: Sequence[str],
    current_text: str,
    protected: Sequence[bool],
    phrase_lookup: PhraseLookup,
    phrase_weight: PhraseWeight,
    personal_lookup: PersonalLookup,
    max_phrase_length: int = 12,
) -> list[DecodedSpan]:
    """Return the best non-overlapping phrase segmentation.

    Explicitly learned personal phrases are strongest.  Bundled phrases then
    maximize exact-reading coverage, followed by longer coherent spans and
    source frequency.  Single characters remain a lossless fallback, so the
    decoder never needs an entire sentence to exist as one dictionary row.
    """
    count = len(readings)
    if count != len(current_text) or count != len(protected):
        raise ValueError("readings, text, and protection mask must align")
    if not count:
        return []

    paths: list[_Path | None] = [None] * (count + 1)
    paths[0] = _Path(0, 0, 0, 0.0, ())
    for start in range(count):
        path = paths[start]
        if path is None:
            continue

        # A protected character is an explicit choice in this composition.
        # It forms a hard boundary and cannot be swallowed by a phrase edge.
        single = DecodedSpan(start, start + 1, current_text[start])
        single_path = _Path(
            path.personal_characters,
            path.lexical_characters,
            path.compaction,
            path.frequency_score,
            path.spans + (single,),
        )
        if paths[start + 1] is None or single_path.score > paths[start + 1].score:
            paths[start + 1] = single_path
        if protected[start]:
            continue

        maximum = min(max_phrase_length, count - start)
        for width in range(1, maximum + 1):
            end = start + width
            if any(protected[start:end]):
                break
            span_readings = list(readings[start:end])
            personal = personal_lookup(span_readings)
            candidates = phrase_lookup(span_readings)
            options = ([personal] if personal else []) + candidates
            for phrase in dict.fromkeys(options):
                if len(phrase) != width:
                    continue
                is_personal = bool(personal and phrase == personal)
                weight = max(0, phrase_weight(span_readings, phrase))
                candidate_path = _Path(
                    path.personal_characters + (width if is_personal else 0),
                    path.lexical_characters + (0 if is_personal else width),
                    path.compaction + max(0, width - 1),
                    path.frequency_score + math.log1p(weight),
                    path.spans
                    + (DecodedSpan(start, end, phrase, is_personal),),
                )
                if paths[end] is None or candidate_path.score > paths[end].score:
                    paths[end] = candidate_path

    result = paths[count]
    return list(result.spans) if result is not None else []
