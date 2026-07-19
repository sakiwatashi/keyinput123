import tempfile
import unittest
from pathlib import Path

from bopomofo_core.pinned_store import PinnedStore
from bopomofo_core.session import CandidateSession
from bopomofo_core.state import EventKind


class FakeProvider:
    TABLE = {
        "ㄒㄧㄣˋ": ["信", "釁", "芯"],
        "ㄒㄩㄝˋ": ["血", "雪"],
        "ㄑㄩㄝˋ": ["卻", "確", "雀"],
    }

    def candidates(self, reading):
        return self.TABLE.get(reading, [])


class CandidateSessionTests(unittest.TestCase):
    def test_replacement_after_tone_refreshes_candidates(self) -> None:
        session = CandidateSession(FakeProvider())
        for symbol in "ㄒㄩㄝˋ":
            session.input_symbol(symbol)
        self.assertEqual(["血", "雪"], session.candidates)
        event = session.input_symbol("ㄑ")
        self.assertEqual(EventKind.UPDATED, event.kind)
        self.assertEqual("ㄑㄩㄝˋ", session.preedit)
        self.assertEqual(["卻", "確", "雀"], session.candidates)

    def test_invalid_completed_replacement_bells_and_preserves_state(self) -> None:
        session = CandidateSession(FakeProvider())
        for symbol in "ㄒㄩㄝˋ":
            session.input_symbol(symbol)
        event = session.input_symbol("ㄅ")
        self.assertEqual(EventKind.BELL, event.kind)
        self.assertEqual("ㄒㄩㄝˋ", session.preedit)
        self.assertEqual(["血", "雪"], session.candidates)

    def test_pin_is_persisted_and_always_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pins.json"
            pins = PinnedStore(path)
            pins.pin("ㄒㄧㄣˋ", "芯")
            session = CandidateSession(FakeProvider(), PinnedStore(path))
            for symbol in "ㄒㄧㄣˋ":
                session.input_symbol(symbol)
            self.assertEqual(["芯", "信", "釁"], session.candidates)

    def test_commit_sends_one_selected_character_and_clears(self) -> None:
        session = CandidateSession(FakeProvider())
        for symbol in "ㄒㄧㄣˋ":
            session.input_symbol(symbol)
        event = session.commit_candidate(0)
        self.assertEqual(EventKind.COMMITTED, event.kind)
        self.assertEqual("信", event.committed)
        self.assertEqual("", session.preedit)
        self.assertEqual([], session.candidates)

    def test_candidate_window_is_limited_to_five(self) -> None:
        class ManyCandidatesProvider:
            def candidates(self, reading):
                return list("甲乙丙丁戊己庚辛壬癸")

        session = CandidateSession(ManyCandidatesProvider())
        for symbol in "ㄒㄧㄣˋ":
            session.input_symbol(symbol)
        self.assertEqual(list("甲乙丙丁戊"), session.candidates)

    def test_phrase_ranking_delegates_to_contextual_provider(self) -> None:
        class ContextualProvider(FakeProvider):
            def best_phrase(self, readings):
                return "樹葉" if readings == ["ㄕㄨˋ", "ㄧㄝˋ"] else ""

        session = CandidateSession(ContextualProvider())
        self.assertEqual("樹葉", session.best_phrase(["ㄕㄨˋ", "ㄧㄝˋ"]))

    def test_phrase_ranking_is_optional(self) -> None:
        session = CandidateSession(FakeProvider())
        self.assertEqual("", session.best_phrase(["ㄕㄨˋ", "ㄧㄝˋ"]))


if __name__ == "__main__":
    unittest.main()
