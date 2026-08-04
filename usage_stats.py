#! python3
"""Report usage statistics for the control panel.

The ranking and length rules live in bopomofo_core.usage_store and are asked
for here rather than reimplemented in PowerShell, so the panel can never drift
from what the input method records.

    python usage_stats.py [top-n]

Prints JSON:
    {"tracked": 412, "commits": 1877,
     "by_length": [{"length": 1, "distinct": 210, "commits": 900}, ...],
     "most_used": [{"text": "好", "count": 41, "last": 1785790000}, ...],
     "stale": [...]}
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bopomofo_core.usage_store import UsageStore


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    store = UsageStore(os.path.join(appdata, "PinnedBopomofo", "usage.json"))

    distinct = store.by_length()
    commits = store.totals_by_length()
    lengths = sorted(set(distinct) | set(commits))

    print(json.dumps({
        "tracked": len(store),
        "commits": sum(commits.values()),
        "by_length": [
            {
                "length": length,
                "distinct": distinct.get(length, 0),
                "commits": commits.get(length, 0),
            }
            for length in lengths
        ],
        "most_used": store.most_used(limit=limit),
        "stale": store.stale(limit=limit),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
