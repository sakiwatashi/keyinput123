"""Build the official Taiwan character/word-frequency fallback index.

Sources are the Ministry of Education's 1996 common-language survey tables,
published under Taiwan's Open Government Data License 1.0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path


CHAR_SOURCE_SHA256 = "f50f0f17ff5c4240b955be84a74408fad0659ff5c17bf63c849a7efa5a831b61"
WORD_SOURCE_SHA256 = "8ade7cd812e50ed9d0acc396f5b493d40014e00571b6cd424ae9d812bd1042de"
SOURCE_DATASET = "85年常用語詞調查報告之各項統計表"
SOURCE_URL = "https://data.gov.tw/dataset/45518"
MIN_LENGTH = 2
MAX_LENGTH = 12


def is_cjk(character: str) -> bool:
    code = ord(character)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x323AF
    )


def read_rows(path: Path, expected_sha256: str) -> list[list[str]]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(
            f"Unexpected MOE source SHA-256 for {path}: {digest}"
        )
    # The historical files are Big5-family CSVs with a few obsolete byte
    # sequences. Rows containing replacement characters are filtered below.
    return list(csv.reader(io.StringIO(raw.decode("cp950", errors="replace"))))


def build_index(character_csv: Path, word_csv: Path) -> dict[str, object]:
    character_weights: dict[str, int] = {}
    for row in read_rows(character_csv, CHAR_SOURCE_SHA256)[1:]:
        if len(row) < 5:
            continue
        character = row[1]
        try:
            weight = int(row[4])
        except ValueError:
            continue
        if len(character) == 1 and is_cjk(character):
            character_weights[character] = max(
                weight, character_weights.get(character, 0)
            )

    phrases: dict[str, int] = {}
    for row in read_rows(word_csv, WORD_SOURCE_SHA256)[1:]:
        if len(row) < 3:
            continue
        phrase = row[1]
        try:
            weight = int(row[2])
        except ValueError:
            continue
        if (
            MIN_LENGTH <= len(phrase) <= MAX_LENGTH
            and all(is_cjk(character) for character in phrase)
        ):
            phrases[phrase] = max(weight, phrases.get(phrase, 0))

    buckets: dict[int, dict[str, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for phrase, weight in phrases.items():
        buckets[len(phrase)][phrase[0]].append((phrase, weight))
    encoded = {
        str(length): {
            first: [
                list(row)
                for row in sorted(rows, key=lambda item: (-item[1], item[0]))
            ]
            for first, rows in sorted(first_buckets.items())
        }
        for length, first_buckets in sorted(buckets.items())
    }
    return {
        "meta": {
            "source": SOURCE_DATASET,
            "source_url": SOURCE_URL,
            "license": "Open Government Data License 1.0",
            "character_source_sha256": CHAR_SOURCE_SHA256,
            "word_source_sha256": WORD_SOURCE_SHA256,
            "character_count": len(character_weights),
            "phrase_count": len(phrases),
        },
        "characters": character_weights,
        "buckets": encoded,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("character_csv", type=Path)
    parser.add_argument("word_csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = build_index(args.character_csv, args.word_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    meta = index["meta"]
    print(
        f"Wrote {meta['character_count']} characters and "
        f"{meta['phrase_count']} phrases to {args.output}"
    )


if __name__ == "__main__":
    main()
