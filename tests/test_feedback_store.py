import json
import tempfile
import unittest
from pathlib import Path

from bopomofo_core.feedback_store import FeedbackStore


class FeedbackStoreTests(unittest.TestCase):
    def test_records_only_explicit_differences_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feedback.json"
            store = FeedbackStore(path)
            store.record(["ㄧㄡˉ", "ㄏㄨㄚˋ"], "優話", "優化")
            store.record(["ㄧㄡˉ", "ㄏㄨㄚˋ"], "優話", "優化")
            store.record(["ㄗˋ"], "字", "字")

            entries = FeedbackStore(path).entries()
            self.assertEqual(1, len(entries))
            self.assertEqual("優話", entries[0]["converted"])
            self.assertEqual("優化", entries[0]["expected"])
            self.assertEqual(2, entries[0]["count"])

    def test_never_stores_surrounding_text_or_application_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feedback.json"
            FeedbackStore(path).record(["ㄗˋ"], "自", "字")
            raw = json.loads(path.read_text(encoding="utf-8"))
            entry = raw["entries"][0]
            self.assertEqual(
                {"id", "readings", "converted", "expected", "count", "last_seen"},
                set(entry),
            )

    def test_remove_is_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feedback.json"
            store = FeedbackStore(path)
            store.record(["ㄗˋ"], "自", "字")
            identifier = str(store.entries()[0]["id"])
            store.remove({identifier})
            self.assertEqual([], FeedbackStore(path).entries())


if __name__ == "__main__":
    unittest.main()
