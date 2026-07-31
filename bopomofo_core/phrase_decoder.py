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
    covered_characters: int
    compaction: int
    frequency_score: float
    personal_characters: int
    spans: tuple[DecodedSpan, ...]

    @property
    def score(self) -> tuple[int, int, float, int]:
        """Coverage, then span length, then frequency, then personal origin.

        Personal origin is the last tiebreaker rather than the first. Ranking
        it first made any learned pair unbeatable, so a phrase learned in one
        context could dismantle a far stronger word somewhere else: 電話
        (weight 50001) lost to a learned 化一 (weight 0) simply because the
        latter was personal, and 電話一 came out as 店化一. A personal phrase
        still wins its own span -- see the weight it is given below -- but it
        no longer makes that span more attractive than the lexicon says it is.
        """
        return (
            self.covered_characters,
            self.compaction,
            self.frequency_score,
            self.personal_characters,
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

    Segmentations are compared by exact-reading coverage, then by how much of
    that coverage comes from longer coherent spans, then by source frequency.
    Single characters remain a lossless fallback, so the decoder never needs
    an entire sentence to exist as one dictionary row.

    An explicitly learned personal phrase always wins its own span: it is
    scored just above the strongest bundled option for the same readings.
    It is deliberately not scored higher than that, so a phrase learned in one
    context cannot outbid an unrelated, much stronger word next to it.
    """
    count = len(readings)
    if count != len(current_text) or count != len(protected):
        raise ValueError("readings, text, and protection mask must align")
    if not count:
        return []

    paths: list[_Path | None] = [None] * (count + 1)
    paths[0] = _Path(0, 0, 0.0, 0, ())
    for start in range(count):
        path = paths[start]
        if path is None:
            continue

        # A protected character is an explicit choice in this composition.
        # It forms a hard boundary and cannot be swallowed by a phrase edge.
        single = DecodedSpan(start, start + 1, current_text[start])
        single_path = _Path(
            path.covered_characters,
            path.compaction,
            path.frequency_score,
            path.personal_characters,
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
            best_bundled = 0
            for option in candidates:
                if len(option) == width:
                    best_bundled = max(
                        best_bundled, max(0, phrase_weight(span_readings, option))
                    )
            for phrase in dict.fromkeys(options):
                if len(phrase) != width:
                    continue
                is_personal = bool(personal and phrase == personal)
                if is_personal:
                    # The user's answer for this span outranks every bundled
                    # option for the same span, and nothing more. Giving it an
                    # unbounded weight would let a pair learned elsewhere
                    # outbid a much stronger neighbouring word and change text
                    # the user never chose.
                    weight = best_bundled + 1
                else:
                    weight = max(0, phrase_weight(span_readings, phrase))
                candidate_path = _Path(
                    path.covered_characters + width,
                    path.compaction + max(0, width - 1),
                    path.frequency_score + math.log1p(weight),
                    path.personal_characters + (width if is_personal else 0),
                    path.spans
                    + (DecodedSpan(start, end, phrase, is_personal),),
                )
                if paths[end] is None or candidate_path.score > paths[end].score:
                    paths[end] = candidate_path

    result = paths[count]
    return list(result.spans) if result is not None else []
