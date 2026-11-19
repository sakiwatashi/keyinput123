#! python3
"""詞語排序：詞網格、個人詞、詞頻、整句修正。

從 pinned_bopomofo_ime.py 拆出來的 mixin，方法原封不動。它讀寫的
self.segments、self.session、各個 store 都在 PinnedBopomofoTextService.__init__
建立；這裡只放「這段讀音該排成什麼字」的邏輯，不碰按鍵與 PIME 介面。
自動組字與候選視窗必須共用 _ranked_phrase_options 這一份排序（見
AI_MAINTENANCE.md 受保護的互動契約）。
"""

from __future__ import annotations

from .bopomofo_core.hidden_characters import (
    shared_hidden_characters as HIDDEN_CHARACTERS,
)
from .bopomofo_core.keymap import is_typable_reading
from .bopomofo_core.phrase_decoder import decode_phrase_lattice
from .bopomofo_core.phrase_store import MAX_PHRASE_LENGTH, MIN_PHRASE_LENGTH

# 你自己用過一次值多少詞庫權重。詞庫權重的量級是 0 到二十萬，一步(5813) 對
# 一部(21778) 差一萬六，所以八次左右能翻過來——夠快到有感，又不會第一次就
# 搶走一個常用詞。
WORD_USE_BONUS = 2000
# 用過幾次才算習慣。一次跟隨手送出的錯字分不開——個人偏好無條件覆寫詞庫，
# 正是「部要」「下一不」那一類問題的來源。
WORD_USE_CONFIDENCE = 3



class PhraseRankingMixin:
    def _ranked_phrase_options(self, start: int, end: int) -> list[str]:
        """Return one shared ranking for automatic text and candidate UI.

        Personal phrases win equal spans. For the whole buffer, conservative
        reading-aware and exact typo corrections are then promoted ahead of
        their uncorrected source sentences. Taiwan/frequency-backed phrases
        follow, then the conversion engine. Unverified engine guesses are
        allowed only for the whole buffer, where they represent the engine's
        sentence-level default; intermediate guesses must be known words.
        """
        if start < 0 or end > len(self.segments) or end - start < 2:
            return []
        # Every caller ends up asking libchewing about these readings, and a
        # literal ASCII segment has none it can answer for. _apply_phrase_ranking
        # already splits the buffer at those, but _build_candidate_choices picks
        # its own spans -- pressing Down with the caret near a 我們=好 crossed
        # one and raised straight out of onKeyDown, losing the whole composition.
        # Guarding the shared entry point covers both, and any span chosen later.
        if not all(
            is_typable_reading(segment.reading)
            for segment in self.segments[start:end]
        ):
            return []
        readings = [segment.reading for segment in self.segments[start:end]]
        context = self.segments[start - 1].text[-1] if start > 0 else ""
        personal, _contextual = self._personal_phrase(readings, context)
        frequent = self.session.validated_frequent_phrase_candidates(
            readings,
            [segment.candidates for segment in self.segments[start:end]],
        )
        whole_buffer = start == 0 and end == len(self.segments)
        trusted = self.session.trusted_phrase_candidates(readings)
        engine = [
            phrase
            for phrase in self.session.phrase_candidates(readings)
            if whole_buffer
            or phrase in trusted
            or self.session.is_frequent_phrase(phrase)
        ]
        corrected: list[str] = []
        contextual: list[str] = []
        current_text = "".join(
            segment.text for segment in self.segments[start:end]
        )
        if whole_buffer:
            protected = [segment.locked for segment in self.segments[start:end]]
            context_protected = list(protected)
            has_lexical_span = False
            # Exact phrases chosen by the lattice are reliable context, even
            # when the whole sentence is assembled from several dictionary
            # rows. Fuzzy correction may work around them, but must not turn
            # 層數+較高 back into an unrelated whole-engine guess.
            decoded = decode_phrase_lattice(
                readings,
                current_text,
                protected,
                self.session.lexical_phrase_candidates,
                self._weighted_phrase,
                self._personal_phrase,
                MAX_PHRASE_LENGTH,
                pair_score=self._pair_score,
                language_model=self.language_model,
                reading_share=self._reading_share,
            )
            for span in decoded:
                if span.end - span.start < 2 or span.text != current_text[
                    span.start : span.end
                ]:
                    continue
                has_lexical_span = True
                for index in range(span.start, span.end):
                    context_protected[index] = True
            if has_lexical_span:
                for source in engine:
                    if len(source) != len(current_text):
                        continue
                    hybrid = "".join(
                        current if is_protected else suggested
                        for current, suggested, is_protected in zip(
                            current_text, source, context_protected
                        )
                    )
                    if (
                        hybrid != current_text
                        and all(
                            is_protected
                            or suggested in segment.candidates
                            for suggested, segment, is_protected in zip(
                                source,
                                self.segments[start:end],
                                context_protected,
                            )
                        )
                        and hybrid not in contextual
                    ):
                        contextual.append(hybrid)
            # Re-decode both the visible text and the exact-reading sources.
            # On the next render the visible text may already be corrected;
            # retaining the engine sources here makes the corrected sentence
            # reproducible as candidate zero instead of a one-frame mutation.
            for source in dict.fromkeys([current_text] + frequent + engine):
                if len(source) != end - start:
                    continue
                suggestion, phonetic_changes = self.phonetic_corrector.correct(
                    readings,
                    source,
                    protected,
                    self.session.candidates_for_reading,
                    self.session.frequent_phrase_candidates,
                    known_phrase_lookup=(
                        self.session.trusted_phrase_candidates
                    ),
                    replacement_phrase_lookup=(
                        self.session.trusted_phrase_candidates
                    ),
                    # 模糊路徑只認詞庫。trusted 那一份包含「引擎認得又夠常見」
                    # 的後備，而引擎在被問一個猜出來的讀音時不管聲調照樣回答，
                    # 於是「六扇門」會變成「六三門」。
                    fuzzy_evidence_lookup=(
                        self.session.lexical_phrase_candidates
                    ),
                    allow_fuzzy=self.phonetic_correction,
                )
                suggestion, typo_changes = self.autocorrector.correct(
                    suggestion, protected
                )
                if (
                    suggestion != source
                    and (phonetic_changes or typo_changes)
                    and all(
                        not is_protected or suggested == current
                        for suggested, current, is_protected in zip(
                            suggestion, current_text, context_protected
                        )
                    )
                    and suggestion not in corrected
                ):
                    corrected.append(suggestion)
        trusted_current = current_text in trusted
        trusted_front = trusted if trusted_current else []
        trusted_tail = [] if trusted_current else trusted

        return [
            phrase
            for phrase in dict.fromkeys(
                ([personal] if personal else [])
                + self._favoured_words(readings)
                + trusted_front
                + corrected
                + frequent
                + trusted_tail
                + [current_text]
                + contextual
                + engine
            )
            if len(phrase) == end - start
        ]

    def _forget_conflicting_phrases(self, start: int, end: int, text: str) -> None:
        """把跟這次選擇牴觸的個人詞條丟掉。

        使用者明確選了別的字，就等於說「蓋在這裡的那筆記錄是錯的」。不丟掉的話
        它下一次組字又會贏回來，而使用者的修正只會落在 pins.json（單字）或另一個
        讀音鍵上，永遠碰不到病灶——實測就是這樣一直來回選「不」和「步」。

        掃過每一個涵蓋這次選擇、寬度在詞庫範圍內的跨度。最多 12x12 次字典查詢，
        而且只在使用者親手選字時才跑。
        """
        for span_start in range(max(0, end - MAX_PHRASE_LENGTH), start + 1):
            for span_end in range(
                max(span_start + MIN_PHRASE_LENGTH, end),
                min(len(self.segments), span_start + MAX_PHRASE_LENGTH) + 1,
            ):
                readings = [
                    segment.reading
                    for segment in self.segments[span_start:span_end]
                ]
                remembered = self.phrase_store.exact(readings)
                if not remembered:
                    continue
                # 只怪罪畫面上這段文字真正的來源。
                #
                # 第一版只要條目在被改的位置上跟新選擇不同就刪，於是使用者在
                # 別的詞裡選一個字，會連帶刪掉一個剛好涵蓋同一段讀音、但跟畫面
                # 無關的條目。實測損失了 `ㄧˉ ㄅㄨˋ -> 一步`：使用者在某處選了
                # 「不」，而那筆條目當時根本沒有參與組字。
                current = "".join(
                    segment.text
                    for segment in self.segments[span_start:span_end]
                )
                if remembered != current:
                    continue
                chosen = remembered[start - span_start : end - span_start]
                if chosen != text:
                    self.phrase_store.forget(readings)

    def _favoured_words(self, readings: list[str]) -> list[str]:
        """你自己用得夠多的詞，排在詞庫前面。

        用過一次不算——那跟隨手送出的錯字分不開，而個人偏好無條件覆寫詞庫正是
        「部要」「下一不」那一類問題的來源。要連續用到 WORD_USE_CONFIDENCE 次，
        而且是這段讀音底下用得最多的那個，才排到前面。

        這是詞的層級，所以沒有同音歧義：「不要」和「下一步」的讀音串不同，各自
        累積，不會互相干擾。字的層級做不到這件事。
        """
        counts = self.word_usage.words_for(readings)
        if not counts:
            return []
        word, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        if count < WORD_USE_CONFIDENCE:
            return []
        return [word]

    def _record_word_usage(self) -> None:
        """把這次送出的文字切成已知的詞，每個記一次。

        用最長匹配掃過送出的內容，而不是重跑詞網格。送出時每一格通常都是 locked
        （使用者選過或詞彙鎖定過），而 locked 在詞網格裡是硬邊界——重跑只會得到
        一串單字，一個詞都記不到。這裡要的也不是「網格覺得該怎麼切」，而是「送出
        的這段文字由哪些已知的詞組成」。

        只記兩個字以上、而且詞庫或個人詞庫真的認得的跨度。認不得的就跳過一格，
        不要把隨機的字組當成詞餵進去。
        """
        if len(self.segments) < MIN_PHRASE_LENGTH:
            return
        readings = [segment.reading for segment in self.segments]
        text = "".join(segment.text for segment in self.segments)
        index = 0
        while index < len(readings):
            widest = min(MAX_PHRASE_LENGTH, len(readings) - index)
            for width in range(widest, MIN_PHRASE_LENGTH - 1, -1):
                span_readings = readings[index : index + width]
                span_text = text[index : index + width]
                if not all(
                    is_typable_reading(reading) for reading in span_readings
                ):
                    continue
                known = span_text in self.session.lexical_phrase_candidates(
                    span_readings
                ) or self.phrase_store.exact(span_readings) == span_text
                if known:
                    self.word_usage.record(span_readings, span_text)
                    index += width
                    break
            else:
                index += 1

    def _reading_share(self, readings: list[str], word: str) -> float:
        """這個讀音佔這個字詞的比例；問不到就當只有一個讀音。"""
        share = getattr(self.session.provider, "reading_share", None)
        if share is None:
            return 1.0
        try:
            return share(readings, word)
        except Exception:
            return 1.0

    def _pair_score(self, left: str, text: str) -> float:
        """詞網格每一種切法都會問這個；算壞了就當沒有上下文，不能擋住打字。"""
        try:
            return self.pair_store.bonus(left, text)
        except Exception:
            return 0.0

    def _weighted_phrase(self, readings: list[str], phrase: str) -> int:
        """詞庫權重加上你自己用過幾次。

        內建權重是全語料的統計，這一項是你的。兩個都是「這個詞有多常見」，只是
        母體不同，所以直接相加而不是誰覆寫誰——用得夠多就贏得過詞庫，用得不多
        就只是往前挪一點。

        每次 WORD_USE_BONUS 的量級是照詞庫權重的尺度挑的：一步(5813) 對
        一部(21778) 差一萬六，用個八次就能翻過來。個人偏好該在「用了幾次」之後
        生效，不是第一次就搶走。
        """
        base = self.session.phrase_weight(readings, phrase)
        return base + self.word_usage.count(readings, phrase) * WORD_USE_BONUS

    def _personal_phrase(self, readings: list[str], context: str) -> tuple[str, bool]:
        """The user's word for these readings, and whether the context backs it.

        Context wins when it exists: 寫→程式 and 座→城市 are recorded
        separately, so one of them can no longer wreck the other's sentence.

        Falling back to the context-free memory keeps every phrase already in
        phrases.json working. It simply stops being able to overrule a far more
        common word without evidence that it belongs in this particular spot --
        the decoder decides that, see PERSONAL_OVERRIDE_RATIO.
        """
        remembered = self.context_store.lookup(readings, context)
        if remembered:
            return (remembered, True)
        return (self.phrase_store.exact(readings), False)

    def _learn_context(self, start: int, end: int, text: str) -> None:
        """Record what the user chose here, and what it followed.

        Only spans the user actually corrected reach this. Learning from the
        engine's own guesses would fill the store with the defaults it already
        produces, and then confirm them forever.
        """
        if start <= 0 or not MIN_PHRASE_LENGTH <= end - start <= MAX_PHRASE_LENGTH:
            return
        self.context_store.learn(
            [segment.reading for segment in self.segments[start:end]],
            text,
            self.segments[start - 1].text[-1],
        )

    def _typable_runs(self) -> list[tuple[int, int]]:
        """Maximal spans of segments whose readings are real Bopomofo.

        A literal ASCII segment inserted mid-composition -- ``我們=好`` -- has
        no reading libchewing can be asked about, and handing it one raised
        straight out of onKeyDown, taking the whole uncommitted composition
        with it. It is also a genuine phrase boundary: 我們=好 is not a word.

        Ranking each run on its own therefore fixes the crash and keeps the
        correction the user actually wants -- 我們 on the left still gets it,
        instead of the whole buffer silently losing phrase ranking as soon as
        one symbol appears anywhere in it.
        """
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for index, segment in enumerate(self.segments):
            if is_typable_reading(segment.reading):
                if start is None:
                    start = index
            elif start is not None:
                runs.append((start, index))
                start = None
        if start is not None:
            runs.append((start, len(self.segments)))
        return runs

    def _apply_phrase_ranking(self) -> None:
        """Decode every unlocked span, then apply whole-sentence correction."""
        if len(self.segments) < 2:
            return
        for start, end in self._typable_runs():
            if end - start < 2:
                continue
            self._apply_phrase_lattice(start, end)
            options = self._ranked_phrase_options(start, end)
            default = options[0] if options else ""
            if default:
                self._apply_ranked_phrase(end - start, default, end=end)

    def _apply_phrase_lattice(self, start: int = 0, end: int | None = None) -> None:
        """Compose one sentence from multiple exact-reading common words."""
        if end is None:
            end = len(self.segments)
        window = self.segments[start:end]
        readings = [segment.reading for segment in window]
        current_text = "".join(segment.text for segment in window)
        # 只有親手選的字是硬邊界；自動比對來的個人詞鎖每一輪都放開重算。
        protected = [
            segment.locked and not segment.auto_locked for segment in window
        ]
        for segment in window:
            if segment.auto_locked:
                segment.locked = False
                segment.auto_locked = False
        spans = decode_phrase_lattice(
            readings,
            current_text,
            protected,
            self.session.lexical_phrase_candidates,
            self._weighted_phrase,
            self._personal_phrase,
            MAX_PHRASE_LENGTH,
            pair_score=self._pair_score,
            language_model=self.language_model,
            reading_share=self._reading_share,
        )
        for span in spans:
            # 「一律隱藏」的字不能從這裡溜進組字區。詞網格是直接把選中的字寫進
            # 去的，繞過候選字過濾——實測把「喫」加進隱藏名單完全沒有效果，因為
            # 擋的是候選清單，而畫面上的字根本不是從那裡來的。
            if any(HIDDEN_CHARACTERS.is_hidden(c) for c in span.text):
                continue
            # decode_phrase_lattice indexes the window it was given, so shift
            # back to buffer coordinates before writing.
            for segment, character in zip(
                self.segments[start + span.start : start + span.end], span.text
            ):
                if segment.locked:
                    continue
                segment.candidates = list(
                    dict.fromkeys([character] + segment.candidates)
                )[: self.session.max_candidates]
                segment.selected = 0
                if span.personal:
                    segment.locked = True
                    segment.auto_locked = True

    def _apply_ranked_phrase(
        self, width: int, phrase: str, lock: bool = False, end: int | None = None
    ) -> None:
        """Move one phrase to the front without replacing locked segments.

        ``end`` defaults to the end of the buffer, which is where every caller
        wanted it until literal ASCII started splitting the buffer into runs
        that do not reach it.
        """
        if end is None:
            end = len(self.segments)
        start = end - width
        if width < 1 or len(phrase) != width or start < 0 or end > len(self.segments):
            return
        if any(HIDDEN_CHARACTERS.is_hidden(character) for character in phrase):
            return
        for segment, suggested in zip(self.segments[start:end], phrase):
            if segment.locked:
                continue
            segment.candidates = list(
                dict.fromkeys([suggested] + segment.candidates)
            )[: self.session.max_candidates]
            segment.selected = 0
            if lock:
                segment.locked = True
