"""Dynamic-programming decoder for an editable Bopomofo sentence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Sequence


PhraseLookup = Callable[[List[str]], List[str]]
PhraseWeight = Callable[[List[str], str], int]
# (readings, left-context character) -> (phrase, whether the context matched)
PersonalLookup = Callable[[List[str], str], "tuple[str, bool]"]
# (left-context character, span text) -> bonus for how often the user has typed
# these characters next to each other.
PairScore = Callable[[str, str], float]
# (readings, word) -> the share of the word's frequency that belongs to these
# readings (還 under ㄒㄩㄢˊ is a small share of 還). 1.0 for one reading.
ReadingShare = Callable[[List[str], str], float]

# What each dictionary span costs, in the same log units as frequency.
#
# Segmentations used to be ranked by span length before frequency, so any
# two-character word beat two single characters however rare the word was:
# 現在是用 became 現在適用, 是能 became 勢能, 是想 became 試想 -- 是 is among the
# most common characters in the language and still lost to every word it
# could be glued into. Summing log frequencies alone goes wrong the other way
# (more spans always add more), so each span pays a fixed cost instead.
#
# Measured by replaying the user's 1068 confirmed sentences and counting the
# manual selections needed (the old ordering: 898). 0-6 gave 1029, 12 gave
# 936, 16 gave 879, 20 gave 887, 30 and above fell back to 898.
SPAN_COST = 16.0

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


def _best_bundled_split(
    readings: Sequence[str],
    phrase_lookup: PhraseLookup,
    phrase_weight: PhraseWeight,
    max_phrase_length: int,
) -> float:
    """The best score the lexicon alone can give these readings, however split.

    A learned personal phrase has to beat this, not just the bundled words of
    exactly its own width: with a cost per span, two common single characters
    can outscore a lone personal entry, and the user's own 因該 came out as
    因+該 even though they had learned it for exactly these readings.
    """
    count = len(readings)
    best = [-math.inf] * (count + 1)
    best[0] = 0.0
    for start in range(count):
        if best[start] == -math.inf:
            continue
        for width in range(1, min(max_phrase_length, count - start) + 1):
            span = list(readings[start : start + width])
            for option in phrase_lookup(span):
                if len(option) != width:
                    continue
                value = best[start] + math.log1p(max(0, phrase_weight(span, option))) - SPAN_COST
                if value > best[start + width]:
                    best[start + width] = value
    return best[count]


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
    def score(self) -> tuple[int, float, int]:
        """Coverage, then frequency, then personal origin.

        Span length is no longer a separate rank above frequency; it is priced
        into the frequency through SPAN_COST, so a long common word still wins
        but a rare word no longer beats common single characters by default.

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
    pair_score: PairScore | None = None,
    language_model=None,
    reading_share: ReadingShare | None = None,
) -> list[DecodedSpan]:
    """Return the best non-overlapping phrase segmentation.

    Segmentations are compared by exact-reading coverage, then by source
    frequency with a fixed cost per span (SPAN_COST), plus -- when
    ``pair_score`` is given -- how often the user has typed each pair of
    adjacent characters, including across span boundaries.
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
    if language_model is not None:
        return _decode_with_language_model(
            readings, current_text, protected, phrase_lookup, phrase_weight,
            personal_lookup, max_phrase_length, pair_score, language_model,
            reading_share or (lambda span, word: 1.0),
        )

    paths: list[_Path | None] = [None] * (count + 1)
    paths[0] = _Path(0, 0, 0.0, 0, ())
    for start in range(count):
        path = paths[start]
        if path is None:
            continue

        # A protected character is an explicit choice in this composition.
        # It forms a hard boundary and cannot be swallowed by a phrase edge.
        single = DecodedSpan(start, start + 1, current_text[start])
        left = path.spans[-1].text[-1] if path.spans else ""
        single_path = _Path(
            path.covered_characters,
            path.compaction,
            path.frequency_score
            + (pair_score(left, single.text) if pair_score else 0.0),
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
                demoted = False
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
                            demoted = True
                else:
                    weight = max(0, phrase_weight(span_readings, phrase))
                value = math.log1p(weight) - SPAN_COST
                if is_personal and not demoted and width > 1:
                    # Just above the best the lexicon can do for this span in
                    # any split -- enough to win its own span, and nothing
                    # more, so it still cannot dismantle a stronger neighbour.
                    split = _best_bundled_split(
                        span_readings, phrase_lookup, phrase_weight, max_phrase_length
                    )
                    if split > value:
                        value = split + 1e-6
                candidate_path = _Path(
                    path.covered_characters + width,
                    path.compaction + max(0, width - 1),
                    path.frequency_score
                    + value
                    + (pair_score(context, phrase) if pair_score else 0.0),
                    path.personal_characters + (width if is_personal else 0),
                    path.spans
                    + (DecodedSpan(start, end, phrase, is_personal),),
                )
                if paths[end] is None or candidate_path.score > paths[end].score:
                    paths[end] = candidate_path

    result = paths[count]
    return list(result.spans) if result is not None else []


# ---- language-model decoding -------------------------------------------------
#
# With a word-bigram model the best path no longer depends only on where it
# ends but on its last word, so each position keeps the best few paths, one per
# distinct last word. That is the difference that matters: the frequency-only
# decoder kept one path per position, so 我是 could swallow 是 before the model
# ever saw that 了一下 follows. Every constant below was set by replaying the
# user's confirmed sentences and counting manual selections (see the commit).

# Paths kept per position, one per distinct last word. 8 and 16 measured the
# same; fewer starts dropping the path a later word needs.
LANGUAGE_MODEL_BEAM = 8
# What keeping a syllable as the raw text on screen costs, in log units, when
# no dictionary entry covers it. It only has to lose to any real word.
LITERAL_COST = 20.0
# How strongly the left word's context counts against the word's own
# frequency. 1.0 trusts every stored bigram fully.
CONTEXT_WEIGHT = 0.8


def _decode_with_language_model(
    readings, current_text, protected, phrase_lookup, phrase_weight,
    personal_lookup, max_phrase_length, pair_score, model, reading_share,
):
    count = len(readings)

    def base(span_readings, word):
        """ln P(word) for these readings, on the model's scale."""
        lnp = model.unigram_ln(word)
        if lnp is None:
            # A word the model does not have: our own weight, calibrated onto
            # the model's scale on the words both know.
            return math.log(max(0, phrase_weight(span_readings, word)) + 1) + model.oov_offset
        share = reading_share(span_readings, word)
        return lnp + math.log(share) if share > 0 else lnp - 30.0

    def transition(previous, span_readings, word, word_base):
        """ln P(word | previous). A stored bigram is used as it is: mixing the
        unigram back in puts a floor under it, and that floor erased the
        model's evidence that 是了 is rare -- 試了一下 kept coming out 是了一下.
        The reading share is applied to the bigram as well, so a polyphone's
        context probability counts only the share that belongs to this reading.
        """
        if previous:
            bigram = model.bigram_ln(previous, word)
            unigram = model.unigram_ln(word)
            if bigram is not None and unigram is not None:
                # How much this context moves the word away from its usual
                # frequency, scaled by CONTEXT_WEIGHT, on top of the word's own
                # reading-aware frequency.
                return word_base + CONTEXT_WEIGHT * (bigram - unigram)
        return model.log_floor + word_base

    def bonus(left, text):
        return pair_score(left, text) if pair_score else 0.0

    # states[position][last word] = (covered, score, personal chars, spans)
    states: list[dict] = [dict() for _ in range(count + 1)]
    states[0][""] = (0, 0.0, 0, ())

    def offer(position, word, entry):
        best = states[position].get(word)
        if best is None or entry[:3] > best[:3]:
            states[position][word] = entry

    def best_split(start_context, span_readings):
        """The best the lexicon can do for this span in any split, scored with
        the same context -- the bar a personal phrase has to clear."""
        width = len(span_readings)
        best = [-math.inf] * (width + 1)
        last = [start_context] + [""] * width
        best[0] = 0.0
        for i in range(width):
            if best[i] == -math.inf:
                continue
            for w in range(1, width - i + 1):
                sub = list(span_readings[i : i + w])
                for option in phrase_lookup(sub):
                    if len(option) != w:
                        continue
                    value = best[i] + transition(last[i], sub, option, base(sub, option))
                    if value > best[i + w]:
                        best[i + w] = value
                        last[i + w] = option
        return best[width]

    for start in range(count):
        if not states[start]:
            continue
        ranked = sorted(states[start].items(), key=lambda item: item[1][:3], reverse=True)
        for previous, (covered, score, personal_chars, spans) in ranked[:LANGUAGE_MODEL_BEAM]:
            left = spans[-1].text[-1] if spans else ""
            # Keeping what is on screen is always possible, never preferred.
            literal = current_text[start]
            literal_readings = [readings[start]]
            offer(start + 1, literal, (
                covered,
                score + transition(previous, literal_readings, literal, base(literal_readings, literal))
                - LITERAL_COST + bonus(left, literal),
                personal_chars,
                spans + (DecodedSpan(start, start + 1, literal),),
            ))
            if protected[start]:
                continue
            for width in range(1, min(max_phrase_length, count - start) + 1):
                end = start + width
                if any(protected[start:end]):
                    break
                span_readings = list(readings[start:end])
                personal, contextual = personal_lookup(span_readings, left)
                candidates = [c for c in phrase_lookup(span_readings) if len(c) == width]
                scored = {
                    word: transition(previous, span_readings, word, base(span_readings, word))
                    for word in candidates
                }
                options = list(dict.fromkeys(
                    ([personal] if personal and len(personal) == width else []) + candidates
                ))
                for word in options:
                    is_personal = bool(personal and word == personal)
                    if is_personal:
                        own = scored.get(word)
                        if own is None:
                            own = transition(previous, span_readings, word, base(span_readings, word))
                        demoted = False
                        if not contextual and (word in candidates or _is_near_miss(word, candidates)):
                            own_weight = max(0, phrase_weight(span_readings, word))
                            best_weight = max(
                                (max(0, phrase_weight(span_readings, c)) for c in candidates),
                                default=0,
                            )
                            demoted = own_weight * PERSONAL_OVERRIDE_RATIO < best_weight
                        if demoted:
                            value = own
                        else:
                            # Just above the best any lexicon split can do
                            # here -- enough to win its own span, nothing more.
                            bar = best_split(previous, span_readings)
                            if scored:
                                bar = max(bar, max(scored.values()))
                            value = max(own, bar + 1e-6) if bar != -math.inf else own
                    else:
                        value = scored[word]
                    offer(end, word, (
                        covered + width,
                        score + value + bonus(left, word),
                        personal_chars + (width if is_personal else 0),
                        spans + (DecodedSpan(start, end, word, is_personal),),
                    ))

    final = max(states[count].values(), key=lambda entry: entry[:3])
    return _rechunk(list(final[3]), readings, phrase_lookup)


def _rechunk(spans, readings, phrase_lookup):
    """Join adjacent non-personal spans back into the longest lexicon words.

    The model was trained on text its own tokenizer split, so a word it lacks
    (層數) is best decoded as 層|數 -- the right text, as single characters. The
    rest of the input method treats multi-character spans as reliable context,
    so 層|數|較|高 left nothing to protect and an unrelated engine guess
    (曾恕較高) took over. The text is unchanged; only the grouping is restored.
    """
    result = []
    index = 0
    while index < len(spans):
        span = spans[index]
        if span.personal:
            result.append(span)
            index += 1
            continue
        merged = span
        best_end = index
        text = span.text
        for j in range(index + 1, len(spans)):
            if spans[j].personal:
                break
            text += spans[j].text
            start, end = span.start, spans[j].end
            if text in phrase_lookup(list(readings[start:end])):
                merged = DecodedSpan(start, end, text)
                best_end = j
        result.append(merged)
        index = best_end + 1
    return result
