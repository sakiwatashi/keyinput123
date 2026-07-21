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

    def test_practical_candidate_tail_is_limited_to_twenty(self) -> None:
        class ManyCandidatesProvider:
            def candidates(self, reading):
                return list("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地")

        session = CandidateSession(ManyCandidatesProvider())
        for symbol in "ㄒㄧㄣˋ":
            session.input_symbol(symbol)
        self.assertEqual(20, len(session.candidates))
        self.assertEqual(list("甲乙丙丁戊"), session.candidates[:5])

    def test_phrase_ranking_delegates_to_contextual_provider(self) -> None:
        class ContextualProvider(FakeProvider):
            def best_phrase(self, readings):
                return "樹葉" if readings == ["ㄕㄨˋ", "ㄧㄝˋ"] else ""

            def phrase_candidates(self, readings):
                return ["樹葉", "樹液", "數夜"]

            def dictionary_phrase_candidates(self, readings):
                return ["樹葉", "樹液"]

            def frequent_phrase_candidates(self, candidate_columns):
                return ["樹葉", "數夜"]

        session = CandidateSession(ContextualProvider())
        self.assertEqual("樹葉", session.best_phrase(["ㄕㄨˋ", "ㄧㄝˋ"]))
        self.assertEqual(
            ["樹葉", "樹液", "數夜"],
            session.phrase_candidates(["ㄕㄨˋ", "ㄧㄝˋ"]),
        )
        self.assertEqual(
            ["樹葉", "樹液"],
            session.dictionary_phrase_candidates(["ㄕㄨˋ", "ㄧㄝˋ"]),
        )
        self.assertEqual(
            ["樹葉", "數夜"],
            session.frequent_phrase_candidates([["樹", "數"], ["葉", "夜"]]),
        )

    def test_phrase_ranking_is_optional(self) -> None:
        session = CandidateSession(FakeProvider())
        self.assertEqual("", session.best_phrase(["ㄕㄨˋ", "ㄧㄝˋ"]))
        self.assertEqual([], session.phrase_candidates(["ㄕㄨˋ", "ㄧㄝˋ"]))
        self.assertEqual(
            [], session.dictionary_phrase_candidates(["ㄕㄨˋ", "ㄧㄝˋ"])
        )
        self.assertEqual(
            [], session.frequent_phrase_candidates([["樹"], ["葉"]])
        )

    def test_user_pin_outranks_the_bundled_default(self) -> None:
        class ProtectedProvider(FakeProvider):
            TABLE = {"ㄗˋ": ["自", "字"]}

            def prioritize_candidates(self, reading, candidates):
                if reading == "ㄗˋ":
                    return ["字"] + [item for item in candidates if item != "字"]
                return candidates

        pins = PinnedStore()
        pins.pin("ㄗˋ", "自")
        session = CandidateSession(ProtectedProvider(), pins)
        for symbol in "ㄗˋ":
            session.input_symbol(symbol)
        self.assertEqual(["自", "字"], session.candidates)

    def test_malformed_multi_character_pin_cannot_break_segment_alignment(self) -> None:
        class CharacterProvider(FakeProvider):
            TABLE = {"ㄗˋ": ["字", "自"]}

        pins = PinnedStore()
        pins.pin("ㄗˋ", "不是單字")
        session = CandidateSession(CharacterProvider(), pins)
        for symbol in "ㄗˋ":
            session.input_symbol(symbol)
        self.assertEqual(["字", "自"], session.candidates)
        self.assertTrue(all(len(candidate) == 1 for candidate in session.candidates))

        invalid_pins = PinnedStore()
        invalid_pins.pin("ㄅˋ", "不是單字")
        invalid = CandidateSession(CharacterProvider(), invalid_pins)
        invalid.input_symbol("ㄅ")
        event = invalid.input_symbol("ˋ")
        self.assertEqual(EventKind.BELL, event.kind)
        self.assertEqual("ㄅ", invalid.preedit)

    def test_corrupt_pin_file_falls_back_without_blocking_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pins.json"
            path.write_text("[]", encoding="utf-8")

            pins = PinnedStore(path)

            self.assertEqual([], pins.phrases_for("reading"))
            self.assertEqual(1, len(list(path.parent.glob("pins.corrupt-*.json"))))


if __name__ == "__main__":
    unittest.main()
