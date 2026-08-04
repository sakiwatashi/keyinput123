"""The usage counter must count, survive damage, and stay bounded."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bopomofo_core.usage_store import MAX_ENTRIES, TRIM_TO, UsageStore


class UsageStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "usage.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_counts_single_characters_too(self) -> None:
        # The lexicon only ever holds multi-character phrases, so a counter
        # built on it would report zero single characters. This one counts
        # what was actually committed.
        store = UsageStore(self.path)
        store.record("好")
        store.record("好")
        store.record("你好")
        store.flush(force=True)

        self.assertEqual(store.most_used(limit=1)[0]["text"], "好")
        self.assertEqual(store.most_used(limit=1)[0]["count"], 2)
        self.assertEqual(store.by_length(), {1: 1, 2: 1})
        self.assertEqual(store.totals_by_length(), {1: 2, 2: 1})

    def test_merges_entries_that_differ_only_by_surrounding_space(self) -> None:
        # Commits arrive as text plus suffix, so the same phrase shows up both
        # bare and with a trailing space. Counting them separately splits one
        # phrase in two and dilutes the ranking.
        store = UsageStore(self.path)
        store.record("謝謝")
        store.record("謝謝 ")
        store.record(" 謝謝")
        self.assertEqual(len(store), 1)
        self.assertEqual(store.most_used(limit=1)[0]["count"], 3)
        self.assertEqual(store.by_length(), {2: 1})

    def test_ignores_whitespace_only_commits(self) -> None:
        store = UsageStore(self.path)
        store.record("   ")
        store.record("")
        self.assertEqual(len(store), 0)

    def test_filters_by_length(self) -> None:
        store = UsageStore(self.path)
        for _ in range(5):
            store.record("的")
        store.record("謝謝")
        self.assertEqual(store.most_used(length=2)[0]["text"], "謝謝")
        self.assertEqual([e["text"] for e in store.most_used(length=1)], ["的"])

    def test_survives_a_damaged_file(self) -> None:
        # A broken statistics file must never stop the input method. Losing
        # the counts is acceptable; refusing to start is not.
        self.path.write_text("{ this is not json", encoding="utf-8")
        store = UsageStore(self.path)
        self.assertEqual(len(store), 0)
        store.record("測試")
        store.flush(force=True)
        self.assertEqual(len(UsageStore(self.path)), 1)

    def test_tolerates_unexpected_shapes(self) -> None:
        self.path.write_text(
            json.dumps({"counts": {"甲": 3, "乙": {"n": "x"}, "": {"n": 1}}}),
            encoding="utf-8",
        )
        store = UsageStore(self.path)
        self.assertEqual(store.most_used(limit=5)[0]["text"], "甲")
        self.assertEqual(len(store), 1)

    def test_writes_are_buffered(self) -> None:
        # An fsync per keystroke is what made the keystroke trace a problem.
        store = UsageStore(self.path)
        store.record("一")
        self.assertFalse(self.path.exists(), "第一次記錄就寫檔了，緩衝沒有生效")
        for index in range(30):
            store.record(f"詞{index}")
        self.assertTrue(self.path.exists(), "記錄很多次之後仍然沒有寫檔")

    def test_stays_bounded(self) -> None:
        # Trimming is deliberately hysteretic: it triggers above MAX_ENTRIES
        # and cuts back to TRIM_TO, so the sort does not run on every flush.
        # The invariant is therefore MAX_ENTRIES, not TRIM_TO -- ending at
        # 3180 after 4200 commits is the design working, not a leak.
        store = UsageStore(self.path)
        for index in range(MAX_ENTRIES + 200):
            store.record(f"x{index}")
        store.flush(force=True)
        self.assertLessEqual(len(store), MAX_ENTRIES)
        self.assertLess(len(store), MAX_ENTRIES + 200, "從來沒有修剪過")

    def test_trim_keeps_the_most_used(self) -> None:
        store = UsageStore(self.path)
        for _ in range(50):
            store.record("常用")
        for index in range(MAX_ENTRIES + 200):
            store.record(f"x{index}")
        store.flush(force=True)
        self.assertIn("常用", [e["text"] for e in store.most_used(limit=5)])

    def test_stale_lists_least_recent_first(self) -> None:
        store = UsageStore(self.path)
        store.record("舊")
        store._counts["舊"]["last"] = 1
        store.record("新")
        self.assertEqual(store.stale(limit=1)[0]["text"], "舊")


if __name__ == "__main__":
    unittest.main()
