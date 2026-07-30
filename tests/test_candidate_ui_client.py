from __future__ import annotations

import os
import queue
import time
import unittest

from bopomofo_core.candidate_ui_client import (
    CandidateUiClient,
    default_helper_path,
    encode_hide,
    encode_show,
    mirror_enabled,
    shared_client,
)


def absent_client(**kwargs):
    """A client pointed at a pipe nobody serves, with launching disabled."""
    kwargs.setdefault("pipe_name", r"\\.\pipe\SmartPriorityBopomofoAbsent")
    kwargs.setdefault("launch", False)
    kwargs.setdefault("enabled", True)
    return CandidateUiClient(**kwargs)


class EncodingTest(unittest.TestCase):
    def test_show_line_is_separator_framed(self):
        line = encode_show(["你好", "妳好"], 0)
        self.assertEqual(line, "SHOW\x1f0\x1f你好\x1f妳好\n")

    def test_selection_is_carried(self):
        self.assertTrue(encode_show(["甲", "乙"], 3).startswith("SHOW\x1f3\x1f"))

    def test_hide_line(self):
        self.assertEqual(encode_hide(), "HIDE\n")

    def test_candidates_never_contain_the_separator(self):
        # The framing relies on candidates being natural-language text. If a
        # candidate ever carried the separator the receiver would split it into
        # two entries, so guard the assumption the wire format depends on.
        line = encode_show(["你好", "再見"], 0)
        self.assertEqual(len(line.rstrip("\n").split("\x1f")), 4)


class NonBlockingTest(unittest.TestCase):
    """The mirror must never delay a keystroke.

    PIME's shipped client calls TransactNamedPipe without a timeout and its
    Python server is a single-threaded loop shared by every application, so a
    send that waited on a stalled helper would freeze typing system-wide.
    """

    def test_send_without_a_helper_present_does_not_raise(self):
        client = absent_client()
        client.show(["你好"], 0)
        client.hide()
        client.close()

    def test_send_returns_promptly_when_nothing_is_listening(self):
        client = absent_client()
        start = time.monotonic()
        for index in range(50):
            client.show(["候選%d" % index], 0)
        elapsed = time.monotonic() - start
        client.close()
        self.assertLess(elapsed, 0.5, "queueing candidates must not block")

    def test_full_queue_drops_instead_of_waiting(self):
        client = absent_client()
        # Fill the queue without letting the worker drain it.
        client._ensure_worker()
        while True:
            try:
                client._queue.put_nowait("SHOW\x1f0\x1f塞滿\n")
            except queue.Full:
                break
        start = time.monotonic()
        client.show(["會被丟棄"], 0)
        self.assertLess(time.monotonic() - start, 0.2)
        client.close()

    def test_identical_states_are_not_resent(self):
        client = absent_client()
        client._ensure_worker()
        while not client._queue.empty():
            client._queue.get_nowait()
        client.show(["你好"], 0)
        first = client._queue.qsize()
        client.show(["你好"], 0)
        self.assertEqual(client._queue.qsize(), first)
        client.close()

    def test_empty_candidate_list_hides(self):
        client = absent_client()
        client._ensure_worker()
        while not client._queue.empty():
            client._queue.get_nowait()
        client.show([], 0)
        self.assertEqual(client._queue.get_nowait(), encode_hide())
        client.close()


class HelperLaunchTest(unittest.TestCase):
    def test_helper_path_sits_beside_the_module(self):
        # The installer copies the executable into <module>/helper/, so the
        # module must resolve it from its own location rather than a fixed path.
        path = default_helper_path()
        self.assertTrue(path.endswith(os.path.join("helper", "SmartPriorityCandidateUI.exe")))
        self.assertTrue(os.path.isabs(path))

    def test_missing_helper_never_raises(self):
        client = absent_client(helper_path=r"C:\nowhere\SmartPriorityCandidateUI.exe", launch=True)
        self.assertFalse(client._try_launch_helper())
        client.close()

    def test_launch_attempts_are_rate_limited(self):
        client = absent_client(helper_path=r"C:\nowhere\SmartPriorityCandidateUI.exe", launch=True)
        self.assertFalse(client._try_launch_helper())
        # The second call must be refused by the interval, not by the missing
        # file, so a permanently absent helper cannot cause a spawn storm.
        client._helper_path = __file__
        self.assertFalse(client._try_launch_helper())
        client.close()

    def test_launch_disabled_does_nothing(self):
        client = absent_client(helper_path=__file__, launch=False)
        self.assertFalse(client._try_launch_helper())
        client.close()


class OptInTest(unittest.TestCase):
    """The mirror is incomplete, so it must be inert until asked for."""

    def _config(self, body: str) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        handle.write(body)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_missing_config_is_disabled(self):
        self.assertFalse(mirror_enabled(r"C:\nowhere\candidate-ui.json"))

    def test_damaged_config_is_disabled(self):
        self.assertFalse(mirror_enabled(self._config("{not json")))

    def test_explicit_false_is_disabled(self):
        self.assertFalse(mirror_enabled(self._config('{"enabled": false}')))

    def test_explicit_true_is_enabled(self):
        self.assertTrue(mirror_enabled(self._config('{"enabled": true}')))

    def test_utf8_bom_is_accepted(self):
        # The toggle script writes this file with Windows PowerShell, which
        # emits a UTF-8 BOM. Reading it as plain utf-8 made json.load fail and
        # the swallowed error turned an enabled switch into a disabled one.
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "wb", suffix=".json", delete=False
        )
        handle.write(b"\xef\xbb\xbf" + b'{"enabled": true, "version": 1}')
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        self.assertTrue(mirror_enabled(handle.name))

    def test_disabled_client_starts_no_thread_and_queues_nothing(self):
        client = CandidateUiClient(
            pipe_name=r"\\.\pipe\SmartPriorityBopomofoAbsent",
            launch=False,
            enabled=False,
        )
        client.show(["不該送出"], 0)
        client.hide()
        self.assertTrue(client._queue.empty())
        self.assertFalse(client._started)
        client.close()


class BeaconReadinessTest(unittest.TestCase):
    """Beacon mode removes the real list from PIME's own window.

    It may therefore only engage on proof that the helper is alive; otherwise
    the candidates would exist nowhere and the user could not pick one.
    """

    def test_not_ready_before_any_successful_write(self):
        self.assertFalse(absent_client().beacon_ready)

    def test_not_ready_when_disabled_even_after_a_write(self):
        client = CandidateUiClient(
            pipe_name=r"\\.\pipe\SmartPriorityBopomofoAbsent",
            launch=False,
            enabled=False,
        )
        client._last_success = time.monotonic()
        self.assertFalse(client.beacon_ready)
        client.close()

    def test_ready_after_a_recent_successful_write(self):
        client = absent_client()
        client._last_success = time.monotonic()
        self.assertTrue(client.beacon_ready)
        client.close()

    def test_readiness_expires(self):
        client = absent_client()
        client._last_success = time.monotonic() - 3600.0
        self.assertFalse(client.beacon_ready)
        client.close()

    def test_write_failure_retracts_readiness_immediately(self):
        client = absent_client()
        client._last_success = time.monotonic()
        self.assertTrue(client.beacon_ready)
        # Draining a real send through the worker against a dead pipe must
        # clear liveness so the next keystroke restores the full list.
        client.show(["會失敗"], 0)
        deadline = time.monotonic() + 3.0
        while client.beacon_ready and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(client.beacon_ready)
        client.close()


class SharedClientTest(unittest.TestCase):
    def test_all_text_services_share_one_mirror(self):
        # PIME builds a text service per connected application, but the helper
        # accepts a single writer; instances must not compete for the pipe.
        self.assertIs(shared_client(), shared_client())


if __name__ == "__main__":
    unittest.main()
