"""Fire-and-forget mirror of the candidate list to the out-of-process window.

The candidate window was moved out of ``PIMETextService.dll`` so that no
unsigned code is mapped into a game process. That leaves the Python layer as
the only component holding the candidate list, so it has to hand the list to
the helper process over a channel of our own.

Two constraints shape this module:

* It must never block. PIME's shipped client calls ``TransactNamedPipe``
  without a timeout, so a slow handler stalls the host application's input
  thread outright, and ``server.py`` is a single-threaded loop serving every
  connected application at once. A write that waits would freeze typing
  everywhere, so every send is queued and dropped rather than awaited.
* It must never touch PIME's own transport. That channel is strict
  request/response with sequence validation and tears the connection down on
  any unexpected message.

Nothing here is ever written to disk: candidate text is private user input.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time

PIPE_NAME = r"\\.\pipe\SmartPriorityBopomofo.CandidateUI"

# The out-of-process window ships enabled: the first real users read an opt-in
# hidden in a JSON file as "the feature was never installed". The default is
# safe because failure falls back, not forward — when the helper is missing or
# will not start, PIME's own signed candidate window stays in charge and typing
# is unaffected. Only an explicit {"enabled": false} turns the mirror off; an
# absent, incomplete, or damaged preference means the default, that is, on.
CONFIG_NAME = "candidate-ui.json"

_FIELD_SEPARATOR = "\x1f"

# Relaunching on every failed write would hammer the disk while the helper is
# deliberately absent, so attempts are spaced out.
_RELAUNCH_INTERVAL_SECONDS = 5.0

_CREATE_NO_WINDOW = 0x08000000


def default_config_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", CONFIG_NAME)


def mirror_enabled(config_path: str | None = None) -> bool:
    """Reads the opt-out switch. Only an explicit false disables.

    Read once when the client is built, never on the typing path, because disk
    access during a key event would stall the host application's input thread.
    Changing it therefore takes effect after PIME restarts.
    """
    path = config_path if config_path is not None else default_config_path()
    try:
        # utf-8-sig, not utf-8: Windows PowerShell writes this file with a BOM,
        # and json.load rejects the BOM as a stray character. Reading it as
        # plain utf-8 made a correctly written preference silently fall back
        # to the default.
        with open(path, "r", encoding="utf-8-sig") as handle:
            return bool(json.load(handle).get("enabled", True))
    except Exception:
        return True


def default_helper_path() -> str:
    """Locates the helper shipped beside this module.

    The installer copies the executable into ``<module>/helper/``, so the path
    is derived from this file rather than from any configured directory. In a
    source checkout the file is absent, and launching simply does not happen.
    """
    module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(module_root, "helper", "SmartPriorityCandidateUI.exe")

# Candidates are natural-language text and never contain control characters,
# so a unit separator frames the message without any escaping.
_SHOW = "SHOW"
_HIDE = "HIDE"


def encode_show(candidates, selection):
    """Builds the wire line for a visible candidate page."""
    fields = [_SHOW, str(int(selection))]
    fields.extend(candidates)
    return _FIELD_SEPARATOR.join(fields) + "\n"


def encode_hide():
    return _HIDE + "\n"


class CandidateUiClient:
    """Pushes candidate state to the helper without ever blocking the caller."""

    def __init__(
        self,
        pipe_name: str = PIPE_NAME,
        queue_size: int = 4,
        helper_path: str | None = None,
        launch: bool = True,
        enabled: bool | None = None,
    ) -> None:
        self._enabled = mirror_enabled() if enabled is None else bool(enabled)
        self._pipe_name = pipe_name
        # A short queue on purpose: only the newest page matters, and an
        # unbounded queue would let a stalled helper accumulate keystrokes.
        self._queue: "queue.Queue[str | None]" = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._started = False
        self._last_line: str | None = None
        self._helper_path = helper_path if helper_path is not None else default_helper_path()
        self._launch = launch
        self._last_launch = 0.0
        # Written by the worker, read by the input-method thread. A plain bool
        # needs no lock, and the reader must never block on one.
        self._connected = False

    @property
    def beacon_ready(self) -> bool:
        """True while the pipe to a live helper is established.

        Beacon mode shrinks PIME's own candidate window to a position marker,
        so the real list exists nowhere else. Claiming readiness while the
        helper is gone would leave the user with an empty box and no way to
        pick a candidate, so this requires an actual connection.

        This is deliberately not a time window. The mirror writes on a worker
        thread, so a check during a key event sees the previous write's
        outcome; expiring on a timer meant that after ordinary thinking time
        the next candidate page silently fell back to PIME's own full list,
        which the user sees as the old row-major menu reappearing at random.
        The pipe handle stays open between writes, so the connection itself is
        the honest signal and a broken helper surfaces on the next write.
        """
        return self._enabled and self._connected

    def warm_up(self) -> None:
        """Establishes the connection before the first candidate page.

        Without this the first page of a session is always drawn by PIME,
        because nothing has been written yet and beacon mode cannot engage.
        """
        if not self._enabled:
            return
        self._last_line = None
        self._offer(encode_hide())

    def _ensure_worker(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run, name="candidate-ui-mirror", daemon=True
        )
        self._thread.start()

    def _offer(self, line: str) -> None:
        # Disabled means fully inert: no thread, no process, no pipe. Typing
        # then behaves exactly as it does without this module present at all.
        if not self._enabled:
            return
        # Identical consecutive states carry no information; skipping them keeps
        # the helper idle while the user is not changing the composition.
        if line == self._last_line:
            return
        self._last_line = line
        self._ensure_worker()
        try:
            self._queue.put_nowait(line)
        except queue.Full:
            # The helper is stalled or gone. Dropping is correct: a candidate
            # page is only useful while it is current, and typing must not wait.
            pass

    def show(self, candidates, selection: int = 0) -> None:
        visible = [text for text in candidates if text]
        if not visible:
            self.hide()
            return
        self._offer(encode_show(visible, selection))

    def hide(self) -> None:
        self._offer(encode_hide())

    def close(self) -> None:
        if not self._started:
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def _try_launch_helper(self) -> bool:
        """Starts the helper if it is not already up. Never raises.

        The helper holds a single-instance mutex, so a duplicate launch from
        another application's text service exits on its own. Failure is a
        supported state: without the helper the input method behaves exactly as
        it does without this mirror.
        """
        if not self._launch or not self._helper_path:
            return False
        now = time.monotonic()
        if now - self._last_launch < _RELAUNCH_INTERVAL_SECONDS:
            return False
        self._last_launch = now
        if not os.path.isfile(self._helper_path):
            return False
        try:
            subprocess.Popen(
                [self._helper_path],
                cwd=os.path.dirname(self._helper_path),
                creationflags=_CREATE_NO_WINDOW,
                close_fds=True,
            )
            return True
        except Exception:
            return False

    def _run(self) -> None:
        handle = None
        while True:
            try:
                line = self._queue.get()
            except Exception:
                return
            if line is None:
                break
            try:
                if handle is None:
                    handle = open(self._pipe_name, "wb", buffering=0)
                handle.write(line.encode("utf-8"))
                self._connected = True
            except Exception:
                # Liveness is retracted immediately, so the very next keystroke
                # goes back to letting PIME draw the full candidate list.
                self._connected = False
                # The helper may not be running at all; that is a supported
                # state. Drop this update, forget the connection, and let the
                # next one retry.
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        pass
                    handle = None
                # A dropped line must not be deduplicated away: if the user
                # retypes the same reading the state would otherwise be
                # suppressed and the window would never catch up.
                self._last_line = None
                # Launching happens here, on the worker thread, so that process
                # creation can never be on the path of a keystroke.
                self._try_launch_helper()
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


_shared_lock = threading.Lock()
_shared_client: CandidateUiClient | None = None


def shared_client() -> CandidateUiClient:
    """Returns the one mirror shared by every text-service instance.

    PIME creates a separate text service per connected application, but the
    helper accepts a single writer and only the focused application produces
    candidates. One client per Python server process therefore matches the
    hardware of the situation, and avoids instances competing for the pipe.
    """
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            _shared_client = CandidateUiClient()
        return _shared_client
