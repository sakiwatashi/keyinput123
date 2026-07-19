"""Candidate session combining the editable syllable, engine, and pins."""

from __future__ import annotations

from typing import Protocol

from .pinned_store import PinnedStore
from .state import BopomofoEditor, Event, EventKind, TONES


class CandidateProvider(Protocol):
    def candidates(self, reading: str) -> list[str]: ...


class CandidateSession:
    def __init__(
        self,
        provider: CandidateProvider,
        pins: PinnedStore | None = None,
        max_candidates: int = 5,
    ) -> None:
        self.provider = provider
        self.pins = pins or PinnedStore()
        self.max_candidates = max_candidates
        self.candidates: list[str] = []
        self.editor = BopomofoEditor(validator=self._validate)

    @property
    def preedit(self) -> str:
        return self.editor.preedit

    def _is_complete(self, reading: str) -> bool:
        return bool(reading) and reading[-1:] in TONES

    def _engine_candidates(self, reading: str) -> list[str]:
        return list(dict.fromkeys(self.provider.candidates(reading)))

    def best_phrase(self, readings: list[str]) -> str:
        converter = getattr(self.provider, "best_phrase", None)
        return converter(readings) if converter is not None else ""

    def _prioritize(self, reading: str, engine_candidates: list[str]) -> list[str]:
        pinned = self.pins.phrases_for(reading)
        return list(dict.fromkeys(pinned + engine_candidates))[: self.max_candidates]

    def _validate(self, reading: str) -> bool:
        if not self._is_complete(reading):
            return True
        return bool(self._engine_candidates(reading) or self.pins.phrases_for(reading))

    def _refresh(self) -> None:
        if not self._is_complete(self.preedit):
            self.candidates = []
            return
        self.candidates = self._prioritize(
            self.preedit, self._engine_candidates(self.preedit)
        )

    def input_symbol(self, symbol: str) -> Event:
        event = self.editor.input_symbol(symbol)
        if event.kind is EventKind.UPDATED:
            self._refresh()
        return event

    def backspace(self) -> Event:
        event = self.editor.backspace()
        self._refresh()
        return event

    def clear(self) -> Event:
        self.candidates = []
        return self.editor.clear()

    def commit_candidate(self, index: int = 0) -> Event:
        if not self.candidates:
            return Event(EventKind.BELL, self.preedit, reason="尚無候選字")
        if index < 0 or index >= len(self.candidates):
            return Event(EventKind.BELL, self.preedit, reason="候選位置無效")
        selected = self.candidates[index]
        self.candidates = []
        return self.editor.commit(selected)

    def pin_candidate(self, index: int = 0) -> Event:
        if not self.candidates or index < 0 or index >= len(self.candidates):
            return Event(EventKind.BELL, self.preedit, reason="沒有可固定的候選字")
        self.pins.pin(self.preedit, self.candidates[index])
        self._refresh()
        return Event(EventKind.UPDATED, self.preedit)
