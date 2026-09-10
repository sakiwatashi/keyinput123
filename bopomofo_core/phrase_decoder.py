"""Dynamic-programming decoder for an editable Bopomofo sentence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Sequence


PhraseLookup = Callable[[List[str]], List[str]]
PhraseWeight = Callable[[List[str], str], int]
# (readings, left-context character) -> (phrase, whether the context matched)
PersonalLookup = Callable[[List[str], str], "tuple[str, bool]"]

# How much more frequent a bundled word may be before a context-free personal
# preference stops overruling it.
#
# Measured against the shipped lexicon. Readings where the user's own pick
# should obviously win sit far below this line -- 計畫/計劃 at 1.0x, 在做/再做
# at 3.6x. Readings where one learned pick was wrecking unrelated sentences sit
# far above it -- 城市/程式 at 36x, 事件/試件 at 75x, 以後/以候 at 252x. The
# gap between 3.6 and 36 is wide enough that the exact value hardly matters.
#
# Being conservative here is cheap: the user only has to pick the word once
# more in that context, and the context store then remembers it for good.
PERSONAL_OVERRIDE_RATIO = 10


def _is_near_miss(phrase: str, candidates: Sequence[str]) -> bool:
    """Whether this looks like a real word with one character wrong.

    A learned string that is not a word, but differs from a bundled word in a
    single position, is almost always that word with one bad conversion in it
    -- committed once while something else was misranked, then learned. 下一不
    against 下一步 is one: nobody says 下一不, and once it was in the personal
    index 下一步 could not be typed at all.

    A string that differs everywhere is the opposite: a name, a coined term,
    the user's own vocabulary. 橙柿 shares no character with 城市, and it has to
    keep winning or the user cannot type their own words.

    So the single differing character is the whole test. It separates "this is
    a corrupted copy of a word" from "this is a different word".
    """
    for candidate in candidates:
        if len(candidate) != len(phrase) or candidate == phrase:
            continue
        differences = sum(a != b for a, b in zip(phrase, candidate))
        if differences == 1:
            return True
    return False


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
            # The left neighbour on the best path to here, not the text
            # currently on screen: that is the word this span would actually
            # follow, and it is what makes 寫|程式 and 座|城市 separable.
            context = path.spans[-1].text[-1] if path.spans else ""
            personal, contextual = personal_lookup(span_readings, context)
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
                    own = max(0, phrase_weight(span_readings, phrase))
                    if not contextual and (
                        phrase in candidates
                        or _is_near_miss(phrase, candidates)
                    ):
                        # No evidence this belongs *here*, only that it was
                        # chosen for these readings once somewhere. That is how
                        # picking 程式 once turned 這座城市很美麗 into
                        # 這座程式很美麗: the pair outranked a word 36 times more
                        # common, in a sentence with nothing to do with it.
                        #
                        # The test is whether the lexicon has an answer for this
                        # span at all, not whether the personal entry is one of
                        # them. An earlier version asked the latter, so a
                        # learned string that is not a word skipped the check
                        # entirely and won unconditionally: 下一不 was committed
                        # once while the engine was misranking 不/步, learned,
                        # and from then on 下一步 could not be typed at all.
                        # Nobody says 下一不 -- a real word must outrank a
                        # non-word for the same sound.
                        #
                        # A span the lexicon knows nothing about is still
                        # exempt. That is the user's own vocabulary -- a name,
                        # a coined term -- and it has no bundled rival to lose
                        # to.
                        if own * PERSONAL_OVERRIDE_RATIO < best_bundled:
                            weight = own
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
