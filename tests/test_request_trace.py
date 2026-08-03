"""The trace must record which callbacks arrive and nothing about what was typed."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from bopomofo_core.request_trace import RequestTrace, LOG_NAME, TRACE_NAME


class RequestTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        previous = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.directory.name
        self.addCleanup(
            lambda: os.environ.__setitem__("APPDATA", previous)
            if previous is not None
            else os.environ.pop("APPDATA", None)
        )
        self.state_root = os.path.join(self.directory.name, "PinnedBopomofo")
        os.makedirs(self.state_root, exist_ok=True)

    def _switch_on(self, *, bom: bool = False) -> None:
        encoding = "utf-8-sig" if bom else "utf-8"
        with open(
            os.path.join(self.state_root, TRACE_NAME), "w", encoding=encoding
        ) as handle:
            json.dump({"enabled": True}, handle)

    def _log(self) -> str:
        path = os.path.join(self.state_root, LOG_NAME)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_off_by_default(self) -> None:
        trace = RequestTrace()
        trace.record({"method": "filterKeyDown", "keyCode": 0x10}, {"return": True})
        self.assertEqual("", self._log())

    def test_records_shift_key_events_when_enabled(self) -> None:
        self._switch_on()
        trace = RequestTrace()
        trace.record({"method": "filterKeyDown", "keyCode": 0x10}, {"return": False})
        trace.record({"method": "filterKeyUp", "keyCode": 0x10}, {"return": True})
        log = self._log()
        self.assertIn("filterKeyDown", log)
        self.assertIn("filterKeyUp", log)
        self.assertIn("Shift", log)
        self.assertIn("passed", log)
        self.assertIn("handled", log)

    def test_never_records_what_was_typed(self) -> None:
        """A key code identifies a character, so only modifiers may be named."""
        self._switch_on()
        trace = RequestTrace()
        trace.record(
            {"method": "filterKeyDown", "keyCode": 0x41, "charCode": ord("a")},
            {"return": True},
        )
        trace.record(
            {"method": "onKeyDown", "keyCode": 0x43, "charCode": ord("c")},
            {"return": True, "compositionString": "ㄏ", "commitString": "好"},
        )
        # Checking a bare letter against the whole line is meaningless -- "a"
        # occurs inside "handled". Check the recorded fields instead.
        rows = [line.split("\t") for line in self._log().splitlines()]
        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertEqual("other", row[2], row)
        log = self._log()
        for secret in ("0x41", "65", "0x43", "67", "ㄏ", "好"):
            self.assertNotIn(secret, log, f"the trace leaked {secret!r}")

    def test_ignores_composition_traffic(self) -> None:
        self._switch_on()
        trace = RequestTrace()
        trace.record({"method": "onCompositionTerminated"}, {"return": True})
        self.assertEqual("", self._log())

    def test_switch_survives_a_bom(self) -> None:
        """PowerShell writes a BOM; json.load fails on it and fails silently."""
        self._switch_on(bom=True)
        trace = RequestTrace()
        trace.record({"method": "onPreservedKey", "guid": "f02200cc"}, {"return": True})
        self.assertIn("onPreservedKey", self._log())

    def test_a_broken_switch_means_off(self) -> None:
        with open(
            os.path.join(self.state_root, TRACE_NAME), "w", encoding="utf-8"
        ) as handle:
            handle.write("{ not json")
        trace = RequestTrace()
        trace.record({"method": "filterKeyDown", "keyCode": 0x10}, {"return": True})
        self.assertEqual("", self._log())


if __name__ == "__main__":
    unittest.main()
