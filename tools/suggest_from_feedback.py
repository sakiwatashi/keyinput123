#!/usr/bin/env python3
"""Suggest high-confidence offline rules from local conversion feedback.

Reads %APPDATA%\\PinnedBopomofo\\feedback.json (or --path) and prints same-
length multi-character corrections that may become:

- common_typos.json surface rules, or
- COMMON_USAGE_RULES reading-backed phrases

Never uploads data. Does not write personal files. Human review is required
before any rule is added; context-dependent pairs such as 的/得/地 and 在/再
are filtered out automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

BLOCKED_SURFACE = {
    ("的", "得"),
    ("得", "的"),
    ("的", "地"),
    ("地", "的"),
    ("得", "地"),
    ("地", "得"),
    ("在", "再"),
    ("再", "在"),
}


def default_feedback_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA is not set")
    return Path(appdata) / "PinnedBopomofo" / "feedback.json"


def load_entries(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def is_blocked_surface(converted: str, expected: str) -> bool:
    if len(converted) != len(expected):
        return True
    for left, right in zip(converted, expected):
        if left != right and (left, right) in BLOCKED_SURFACE:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="feedback.json path (default: %%APPDATA%%\\PinnedBopomofo\\feedback.json)",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="minimum aggregated count to report (default: 1)",
    )
    args = parser.parse_args()
    path = args.path or default_feedback_path()
    if not path.exists():
        print(f"No feedback file at {path}", file=sys.stderr)
        return 1

    surface: Counter[tuple[str, str]] = Counter()
    reading_backed: Counter[tuple[tuple[str, ...], str]] = Counter()
    for entry in load_entries(path):
        converted = entry.get("converted")
        expected = entry.get("expected")
        readings = entry.get("readings")
        count = int(entry.get("count", 1) or 1)
        if not isinstance(converted, str) or not isinstance(expected, str):
            continue
        if len(converted) < 2 or len(converted) != len(expected) or converted == expected:
            continue
        if is_blocked_surface(converted, expected):
            continue
        surface[(converted, expected)] += count
        if (
            isinstance(readings, list)
            and len(readings) == len(expected)
            and all(isinstance(item, str) and item for item in readings)
        ):
            reading_backed[(tuple(readings), expected)] += count

    print(f"# Feedback suggestions from {path}")
    print(f"# Entries contributing multi-char same-length diffs: {sum(surface.values())}")
    print()
    print("## Surface typo candidates (common_typos.json)")
    for (wrong, correct), count in surface.most_common():
        if count < args.min_count:
            continue
        print(
            f'{count:3d}  {{"wrong": "{wrong}", "correct": "{correct}", '
            f'"source": "local_feedback_review"}}'
        )
    print()
    print("## Reading-backed phrase candidates (COMMON_USAGE_RULES)")
    for (readings, phrase), count in reading_backed.most_common():
        if count < args.min_count:
            continue
        reading_tuple = ", ".join(f'"{item}"' for item in readings)
        print(f"{count:3d}  (({reading_tuple}), \"{phrase}\"),")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
