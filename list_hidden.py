#! python3
"""List the characters a given frequency floor would actually hide.

The control panel used to list everything below the threshold, which is not
what gets hidden: characters used by a bundled phrase and spoken particles
survive. At a floor of 7 that is the difference between showing 1482 rows and
the 270 that will really disappear.

The rule lives in `bopomofo_core.hidden_characters` and is asked for here
rather than reimplemented in PowerShell, so the panel can never drift from
what the input method does.

    python list_hidden.py 7

Prints JSON: {"floor": 7, "hidden": [{"character": "眥", "score": 0}, ...],
              "protected": 1212, "below": 1482}
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bopomofo_core.hidden_characters import HiddenCharacters
from bopomofo_core.taiwan_frequency import TaiwanFrequency


def main() -> int:
    floor = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    frequency = TaiwanFrequency()

    if floor <= 0:
        print(json.dumps({"floor": floor, "hidden": [], "protected": 0, "below": 0}))
        return 0

    # Ask the real rule, with the user's own lists applied, so what the panel
    # lists is exactly what the input method will drop.
    store = HiddenCharacters()

    below = [
        character
        for character, score in frequency._characters.items()
        if score < floor
    ]
    hidden = [
        {"character": character, "score": frequency.score(character)}
        for character in below
        if store.is_hidden(character, floor=floor)
    ]
    # Closest to the threshold first: those are the ones worth a second look.
    hidden.sort(key=lambda entry: -entry["score"])

    # protected_scores lets the panel recompute every count for any threshold
    # without asking again. It used to re-run this script on each spinner
    # change, and each run pays Python startup plus a 2 MB index read, so
    # clicking from 0 to 7 froze the window for seconds and looked broken.
    protected_scores = sorted(
        frequency.score(character)
        for character in below
        if not store.is_hidden(character, floor=floor)
    )

    print(json.dumps({
        "floor": floor,
        "hidden": hidden,
        "protected": len(below) - len(hidden),
        "protected_scores": protected_scores,
        "below": len(below),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
