"""Merging one machine's user data into another's.

``tools/backup_user_data.ps1`` already snapshots the state folder and rotates
the archives, but restoring one is a whole-file overwrite: whatever the target
machine learned since that snapshot is simply gone. That is the right shape for
"I broke it, put it back" and the wrong shape for "I type on a desktop and on a
laptop".

Merging is additive. Nothing is dropped because the other side lacked it, so a
merge cannot lose a phrase either machine knew. Only two things change an
existing value: a genuine conflict -- the same reading committed as two
different strings -- which is decided on usage evidence and reported, and the
size caps the stores already enforce.

Every merge here is idempotent and order-independent: merging the same remote
twice equals merging it once, and A into B equals B into A apart from which
side wins a tie. Sync runs repeatedly and often over a network drive that half
succeeds, so a merge that drifts when it runs twice is one that corrupts the
user's only irreplaceable data slowly enough that nobody notices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .phrase_store import MAX_ENTRIES as PHRASE_MAX_ENTRIES
from .storage import load_json_object, save_json_object
from .usage_store import MAX_ENTRIES as USAGE_MAX_ENTRIES, TRIM_TO as USAGE_TRIM_TO

# The files worth carrying between machines. keyevent-trace.json and
# candidate-ui.json are deliberately absent: the trace is a regenerable
# diagnostic, and the candidate window preference describes the machine
# (which anti-cheat, which screen) rather than the person.
PHRASES_NAME = "phrases.json"
PINS_NAME = "pins.json"
USAGE_NAME = "usage.json"
HIDDEN_NAME = "hidden-characters.json"
SYNCED_FILES = (PHRASES_NAME, PINS_NAME, USAGE_NAME, HIDDEN_NAME)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class Conflict:
    """One reading that the two machines committed differently."""

    store: str
    key: str
    kept: str
    dropped: str
    reason: str


@dataclass
class MergeReport:
    added: dict[str, int] = field(default_factory=dict)
    pushed: dict[str, int] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    trimmed: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        """Whether this merge changed anything on *either* side.

        Counting only what flowed into the local machine made the first sync of
        a fresh shared folder report "already identical, nothing to merge"
        while it was in fact seeding that folder with the whole personal
        dictionary. The user is told the sync did nothing, on the one run where
        it did the most.
        """
        return (
            bool(self.conflicts)
            or any(self.added.values())
            or any(self.pushed.values())
            or any(self.trimmed.values())
        )

    def note_added(self, store: str, count: int = 1) -> None:
        if count:
            self.added[store] = self.added.get(store, 0) + count

    def note_pushed(self, store: str, count: int = 1) -> None:
        if count:
            self.pushed[store] = self.pushed.get(store, 0) + count


# ---- usage ------------------------------------------------------------------


def merge_usage(
    local: dict[str, Any], remote: dict[str, Any], report: MergeReport | None = None
) -> dict[str, dict[str, int]]:
    """Combine two usage tables by taking the larger count of each entry.

    Summing is the obvious merge and the wrong one. Sync is not a one-off: the
    same remote snapshot gets merged on every run, and summing turns each entry
    into a counter that inflates without bound until it pins itself to the top
    of the control panel's ranking permanently. ``max`` is idempotent, which
    matters more than exactness here -- these numbers only order a list, and
    they are already an approximation of "how much do I use this".
    """
    report = report or MergeReport()
    merged: dict[str, dict[str, int]] = {}
    for text in set(local) | set(remote):
        here = local.get(text) if isinstance(local.get(text), dict) else {}
        there = remote.get(text) if isinstance(remote.get(text), dict) else {}
        merged[text] = {
            "n": max(_int(here.get("n")), _int(there.get("n"))),
            "last": max(_int(here.get("last")), _int(there.get("last"))),
        }
    report.note_added(USAGE_NAME, len(set(remote) - set(local)))
    report.note_pushed(USAGE_NAME, len(set(local) - set(remote)))

    if len(merged) > USAGE_MAX_ENTRIES:
        ranked = sorted(
            merged.items(),
            key=lambda item: (item[1]["n"], item[1]["last"]),
            reverse=True,
        )
        report.trimmed[USAGE_NAME] = len(merged) - USAGE_TRIM_TO
        merged = dict(ranked[:USAGE_TRIM_TO])
    return merged


def _usage_rank(text: str, usage: dict[str, Any]) -> tuple[int, int]:
    entry = usage.get(text) if isinstance(usage.get(text), dict) else {}
    return (_int(entry.get("n")), _int(entry.get("last")))


# ---- phrases ----------------------------------------------------------------


def merge_phrases(
    local: dict[str, str],
    remote: dict[str, str],
    usage: dict[str, Any] | None = None,
    report: MergeReport | None = None,
) -> dict[str, str]:
    """Union of both phrase indexes, with conflicts settled by usage.

    A conflict is one reading span stored as two different strings, which is
    the interesting case: one machine learned a reading as one word and the
    other as its homophone. There is no timestamp in phrases.json to break the
    tie -- but usage.json already records how often and how recently each
    committed string was actually used, so the machine that types it daily
    keeps its answer.

    Falling back to the local value when there is no usage evidence keeps the
    merge unsurprising: syncing never silently changes what the machine in
    front of you already produces.
    """
    usage = usage or {}
    report = report or MergeReport()
    merged = dict(local)

    added = 0
    for key, incoming in remote.items():
        if not isinstance(incoming, str) or not incoming:
            continue
        current = merged.get(key)
        if current is None:
            merged[key] = incoming
            added += 1
        elif current != incoming:
            here, there = _usage_rank(current, usage), _usage_rank(incoming, usage)
            if there > here:
                merged[key] = incoming
                report.conflicts.append(
                    Conflict(PHRASES_NAME, key, incoming, current, "遠端使用較多")
                )
            else:
                reason = "本機使用較多" if here > there else "沒有使用紀錄，保留本機"
                report.conflicts.append(
                    Conflict(PHRASES_NAME, key, current, incoming, reason)
                )
    report.note_added(PHRASES_NAME, added)
    report.note_pushed(PHRASES_NAME, len(set(local) - set(remote)))

    if len(merged) > PHRASE_MAX_ENTRIES:
        # The store's own cap drops whatever was inserted first, which after a
        # merge is an accident of dict ordering rather than a judgement. Usage
        # evidence is the honest basis for choosing what to lose.
        ranked = sorted(
            merged.items(), key=lambda item: _usage_rank(item[1], usage), reverse=True
        )
        report.trimmed[PHRASES_NAME] = len(merged) - PHRASE_MAX_ENTRIES
        merged = dict(ranked[:PHRASE_MAX_ENTRIES])
    return merged


# ---- pins -------------------------------------------------------------------


def merge_pins(
    local: dict[str, list[str]],
    remote: dict[str, list[str]],
    report: MergeReport | None = None,
) -> dict[str, list[str]]:
    """Union each reading's priority list, local order first.

    A pin list is an explicit ranking the user built by choosing candidates, so
    the two sides are not really in conflict -- they are two sittings' worth of
    preference for the same reading. Concatenating and de-duplicating keeps
    every pin either machine made while leaving the local top choice on top, so
    the first candidate never moves under someone who is mid-sentence.
    """
    report = report or MergeReport()
    merged: dict[str, list[str]] = {}
    added = pushed = 0
    for reading in set(local) | set(remote):
        here = [p for p in local.get(reading, ()) if isinstance(p, str)]
        there = [p for p in remote.get(reading, ()) if isinstance(p, str)]
        ordered: list[str] = []
        for phrase in here + there:
            if phrase not in ordered:
                ordered.append(phrase)
        added += len(set(there) - set(here))
        pushed += len(set(here) - set(there))
        merged[reading] = ordered
    report.note_added(PINS_NAME, added)
    report.note_pushed(PINS_NAME, pushed)
    return merged


# ---- hidden characters ------------------------------------------------------


def merge_hidden(
    local: dict[str, Any], remote: dict[str, Any], report: MergeReport | None = None
) -> dict[str, Any]:
    """Union both filter lists and keep the local frequency floor.

    Union is safe in the direction that matters. ``HiddenCharacters.is_hidden``
    checks ``always_show`` before ``hidden``, so a character one machine hid and
    the other explicitly rescued ends up visible: the explicit choice wins over
    the bulk one. A character wrongly shown costs a candidate slot; one wrongly
    hidden cannot be typed at all.

    The floor stays local because it is tuned against this machine's screen and
    reading habits rather than against the person -- but an unset floor adopts
    the remote value, so a fresh install inherits the setting instead of
    silently starting at zero.
    """
    report = report or MergeReport()

    def characters(source: dict[str, Any], key: str) -> set[str]:
        value = source.get(key)
        if not isinstance(value, list):
            return set()
        return {c for c in value if isinstance(c, str) and len(c) == 1}

    local_hidden = characters(local, "hidden")
    local_always = characters(local, "always_show")
    hidden = local_hidden | characters(remote, "hidden")
    always = local_always | characters(remote, "always_show")

    floor = local.get("minimum_frequency")
    if not isinstance(floor, int) or floor <= 0:
        remote_floor = remote.get("minimum_frequency")
        floor = remote_floor if isinstance(remote_floor, int) and remote_floor > 0 else 0

    report.note_added(
        HIDDEN_NAME, len(hidden - local_hidden) + len(always - local_always)
    )
    report.note_pushed(
        HIDDEN_NAME,
        len(hidden - characters(remote, "hidden"))
        + len(always - characters(remote, "always_show")),
    )

    # 從本機那份複製起走，只覆蓋這裡管的三個鍵。直接回傳一個新字典會把檔案裡
    # 其他欄位默默丟掉——實測就把控制台寫的 "version" 洗掉了。同步不該擅自決定
    # 哪些欄位「沒有用」，那是寫進去的那支程式才知道的事。
    merged = dict(local)
    merged["hidden"] = sorted(hidden)
    merged["always_show"] = sorted(always)
    merged["minimum_frequency"] = floor
    for key, value in remote.items():
        if key not in merged:
            merged[key] = value
    return merged


# ---- whole-directory sync ---------------------------------------------------


def _read_counts(path: Path) -> dict[str, Any]:
    raw = load_json_object(path)
    counts = raw.get("counts", raw)
    return counts if isinstance(counts, dict) else {}


def sync_directories(
    state_root: Path, sync_root: Path, dry_run: bool = False
) -> MergeReport:
    """Merge ``sync_root`` into ``state_root`` and write the result to both.

    Writing the merged result back to the shared folder is what makes this
    converge. If only the local side were updated, two machines would each keep
    re-merging a snapshot that never learned anything from the other, and the
    folder would stay frozen at whichever machine wrote it last.

    Nothing here deletes: a store missing from one side is copied, never
    treated as a deletion. Removing a learned phrase everywhere is the control
    panel's job, where the user can see what they are removing.
    """
    state_root, sync_root = Path(state_root), Path(sync_root)
    report = MergeReport()

    usage = merge_usage(
        _read_counts(state_root / USAGE_NAME),
        _read_counts(sync_root / USAGE_NAME),
        report,
    )
    phrases = merge_phrases(
        load_json_object(state_root / PHRASES_NAME),
        load_json_object(sync_root / PHRASES_NAME),
        usage,
        report,
    )
    pins = merge_pins(
        load_json_object(state_root / PINS_NAME),
        load_json_object(sync_root / PINS_NAME),
        report,
    )
    hidden = merge_hidden(
        load_json_object(state_root / HIDDEN_NAME),
        load_json_object(sync_root / HIDDEN_NAME),
        report,
    )

    if dry_run:
        return report

    payloads = {
        PHRASES_NAME: phrases,
        PINS_NAME: pins,
        USAGE_NAME: {"version": 1, "counts": usage},
        HIDDEN_NAME: hidden,
    }
    for root in (state_root, sync_root):
        for name, value in payloads.items():
            save_json_object(root / name, value, sort_keys=True)
    return report
