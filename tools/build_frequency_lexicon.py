"""Build the offline Taiwan-Traditional high-frequency phrase index.

The source is Rime Essay's weighted vocabulary. Run this with PIME's bundled
Python so its OpenCC installation can convert phrases with ``s2twp.json``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path


SOURCE_REPOSITORY = "https://github.com/rime/rime-essay"
SOURCE_COMMIT = "e9b1a374a6ea015fca5bdd04318924b4483ac35a"
SOURCE_SHA256 = (
    "52e00bd5eed9479198923396bae01d4b5adbb13a3ec9b18e441c50cff8641407",
    "a6f8409c261e5d21bd78e6cbcde8f8e1ef7f68c07ff1c2692c07dd4ff4151cea",
)
MIN_WEIGHT = 500
MIN_LENGTH = 2
MAX_LENGTH = 12
MAX_PER_FIRST_CHARACTER_AND_LENGTH = 200
BATCH_SIZE = 4_000


def is_cjk(character: str) -> bool:
    code = ord(character)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x323AF
    )


def source_rows(path: Path) -> list[tuple[str, int]]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in SOURCE_SHA256:
        raise RuntimeError(
            f"Unexpected Essay source SHA-256: {digest}; expected {SOURCE_SHA256}"
        )
    rows: list[tuple[str, int]] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 2:
                continue
            phrase = fields[0]
            try:
                weight = int(fields[1])
            except ValueError:
                continue
            if (
                weight >= MIN_WEIGHT
                and MIN_LENGTH <= len(phrase) <= MAX_LENGTH
                and all(is_cjk(character) for character in phrase)
            ):
                rows.append((phrase, weight))
    return rows


def taiwanize(rows: list[tuple[str, int]]) -> dict[str, int]:
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError(
            "OpenCC is required. Run with PIME's bundled python.exe."
        ) from exc

    # PIME 1.3's small OpenCC binding prints internal pointers. Suppress that
    # implementation detail while constructing the converter and each batch.
    with contextlib.redirect_stdout(io.StringIO()):
        converter = OpenCC("s2twp.json")

    converted: dict[str, int] = {}
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset : offset + BATCH_SIZE]
        joined = "\n".join(phrase for phrase, _ in batch)
        with contextlib.redirect_stdout(io.StringIO()):
            output = converter.convert(joined)
        phrases = output.split("\n")
        if len(phrases) != len(batch):
            raise RuntimeError("OpenCC changed the number of phrase rows")
        for phrase, (_, weight) in zip(phrases, batch):
            if not (
                MIN_LENGTH <= len(phrase) <= MAX_LENGTH
                and all(is_cjk(character) for character in phrase)
            ):
                continue
            converted[phrase] = max(weight, converted.get(phrase, 0))
    return converted


def build_index(rows: dict[str, int]) -> dict[str, object]:
    buckets: dict[int, dict[str, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for phrase, weight in rows.items():
        buckets[len(phrase)][phrase[0]].append((phrase, weight))

    encoded: dict[str, dict[str, list[list[object]]]] = {}
    entry_count = 0
    for length in sorted(buckets):
        encoded_length: dict[str, list[list[object]]] = {}
        for first_character in sorted(buckets[length]):
            ranked = sorted(
                buckets[length][first_character],
                key=lambda row: (-row[1], row[0]),
            )[:MAX_PER_FIRST_CHARACTER_AND_LENGTH]
            encoded_length[first_character] = [list(row) for row in ranked]
            entry_count += len(ranked)
        encoded[str(length)] = encoded_length

    return {
        "meta": {
            "source": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            "source_sha256": list(SOURCE_SHA256),
            "license": "LGPL-3.0",
            "conversion": "OpenCC s2twp",
            "minimum_weight": MIN_WEIGHT,
            "maximum_bucket_size": MAX_PER_FIRST_CHARACTER_AND_LENGTH,
            "entry_count": entry_count,
        },
        "buckets": encoded,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("essay", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    index = build_index(taiwanize(source_rows(args.essay)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Wrote {index['meta']['entry_count']} phrases to {args.output}"
    )


if __name__ == "__main__":
    main()
