"""Build a compact exact-reading phrase index from McBopomofo data."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path


SOURCE_REPOSITORY = "https://github.com/openvanilla/McBopomofo"
SOURCE_COMMIT = "ee9941a6bdafe0fd58412207c04c1e985dd57b03"
SOURCE_LICENSE = "MIT"
LIBCHEWING_SOURCE_REPOSITORY = "https://github.com/chewing/libchewing-data"
LIBCHEWING_SOURCE_COMMIT = "c44e81aef24b06f1509f19e1be54c99812d0c43f"
LIBCHEWING_SOURCE_LICENSE = "LGPL-2.1-or-later"
RIME_ESSAY_SOURCE_REPOSITORY = "https://github.com/rime/rime-essay"
RIME_ESSAY_SOURCE_COMMIT = "e9b1a374a6ea015fca5bdd04318924b4483ac35a"
RIME_ESSAY_SOURCE_LICENSE = "LGPL-3.0"
TONES = frozenset("ˉˊˇˋ˙")


def normalize_reading(reading: str) -> str:
    """Match the editor's explicit first-tone representation."""
    return reading if reading[-1:] in TONES else reading + "ˉ"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_occurrences(*paths: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                phrase, weight = line.rsplit(maxsplit=1)
                result[phrase] = max(result.get(phrase, 0), int(weight))
            except (TypeError, ValueError):
                continue
    return result


def build_index(
    base_path: Path,
    mappings_path: Path,
    libchewing_tsi_path: Path,
    occurrences_path: Path,
    essay_path: Path,
    reviewed_path: Path,
) -> dict[str, object]:
    # Essay is the broader contemporary language model and therefore wins
    # when both sources score the same spelling. McBopomofo remains the
    # fallback for Taiwan-specific words absent from Essay. The numeric scales
    # are corpus-local, so taking a cross-corpus maximum would be misleading.
    occurrences = read_occurrences(occurrences_path)
    occurrences.update(read_occurrences(essay_path))
    entries: dict[str, dict[str, int]] = defaultdict(dict)

    # McBopomofo keeps its exact single-character readings in BPMFBase.
    # Including them lets the sentence decoder compare word boundaries using
    # the same occurrence scale instead of freezing every engine default.
    for raw_line in base_path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.strip().split()
        if len(parts) < 2 or len(parts[0]) != 1:
            continue
        character = parts[0]
        key = normalize_reading(parts[1])
        entries[key][character] = max(
            entries[key].get(character, 0), occurrences.get(character, 0)
        )

    for raw_line in mappings_path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.strip().split()
        if len(parts) < 3:
            continue
        phrase = parts[0]
        readings = [normalize_reading(reading) for reading in parts[1:]]
        if not 2 <= len(phrase) <= 12 or len(phrase) != len(readings):
            continue
        key = " ".join(readings)
        entries[key][phrase] = max(
            entries[key].get(phrase, 0), occurrences.get(phrase, 0)
        )

    # Current libchewing-data supplies additional Taiwan phrases that are not
    # present in McBopomofo (for example, 新句).  Readings are explicit in the
    # source CSV, so these rows never infer a pronunciation from text alone.
    with libchewing_tsi_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 3 or row[0].startswith("#"):
                continue
            phrase = row[0]
            raw_readings = row[2].split()
            if not 2 <= len(phrase) <= 12 or len(phrase) != len(raw_readings):
                continue
            readings = [normalize_reading(reading) for reading in raw_readings]
            key = " ".join(readings)
            entries[key][phrase] = max(
                entries[key].get(phrase, 0), occurrences.get(phrase, 0)
            )

    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    for row in reviewed.get("entries", []):
        phrase = str(row.get("phrase", ""))
        readings = [
            normalize_reading(str(value)) for value in row.get("readings", [])
        ]
        if not 2 <= len(phrase) <= 12 or len(phrase) != len(readings):
            raise ValueError(f"invalid reviewed phrase row: {row!r}")
        key = " ".join(readings)
        entries[key][phrase] = max(
            entries[key].get(phrase, 0), int(row.get("weight", 0))
        )

    packed = {
        key: [
            [phrase, weight]
            for phrase, weight in sorted(
                phrases.items(), key=lambda item: (-item[1], item[0])
            )[:20]
        ]
        for key, phrases in sorted(entries.items())
    }
    return {
        "meta": {
            "source": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "license": SOURCE_LICENSE,
            "base_sha256": sha256(base_path),
            "mappings_sha256": sha256(mappings_path),
            "occurrences_sha256": sha256(occurrences_path),
            "libchewing_source": LIBCHEWING_SOURCE_REPOSITORY,
            "libchewing_source_commit": LIBCHEWING_SOURCE_COMMIT,
            "libchewing_license": LIBCHEWING_SOURCE_LICENSE,
            "libchewing_tsi_sha256": sha256(libchewing_tsi_path),
            "essay_source": RIME_ESSAY_SOURCE_REPOSITORY,
            "essay_source_commit": RIME_ESSAY_SOURCE_COMMIT,
            "essay_license": RIME_ESSAY_SOURCE_LICENSE,
            "essay_sha256": sha256(essay_path),
            "reviewed_sha256": sha256(reviewed_path),
            "entry_count": sum(len(rows) for rows in packed.values()),
            "reading_count": len(packed),
        },
        "entries": packed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("mappings", type=Path)
    parser.add_argument("libchewing_tsi", type=Path)
    parser.add_argument("occurrences", type=Path)
    parser.add_argument("essay", type=Path)
    parser.add_argument("reviewed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = build_index(
        args.base,
        args.mappings,
        args.libchewing_tsi,
        args.occurrences,
        args.essay,
        args.reviewed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(index, stream, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(index["meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
