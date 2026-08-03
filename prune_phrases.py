#! python3
"""Report or remove personal phrases that a longer entry already covers.

The old learning rule stored every substring of width 2..12 at every position,
so a single twelve-character sentence became about 66 entries. A real store
reached 6912 entries and 477 KB, of which 6535 were fragments contained in a
longer entry.

Run with PIME's bundled Python so the containment rule comes from
`bopomofo_core.phrase_store` rather than being reimplemented elsewhere.

    python prune_phrases.py            # report only, changes nothing
    python prune_phrases.py --apply    # remove them

The store is the user's own data. Reporting is the default so nothing is
deleted without an explicit second step.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bopomofo_core.phrase_store import PhraseStore


def store_path() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "PinnedBopomofo", "phrases.json")


def main() -> int:
    apply = "--apply" in sys.argv
    path = store_path()
    if not os.path.exists(path):
        print(json.dumps({"before": 0, "removable": 0, "after": 0, "applied": False}))
        return 0

    store = PhraseStore(path)
    before = len(store._entries)

    if not apply:
        # Count on a detached copy so a report can never write anything.
        preview = PhraseStore(None)
        preview._entries = dict(store._entries)
        removable = preview.prune_redundant()
        print(json.dumps({
            "before": before,
            "removable": removable,
            "after": before - removable,
            "applied": False,
        }, ensure_ascii=False))
        return 0

    # Keep a copy before touching data the user spent months building.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.before-prune-{stamp}"
    shutil.copy2(path, backup)

    removed = store.prune_redundant()
    print(json.dumps({
        "before": before,
        "removable": removed,
        "after": before - removed,
        "applied": True,
        "backup": backup,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
