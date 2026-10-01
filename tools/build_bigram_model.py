"""Build the bundled word-bigram model from libchewing-data's bigram_p50.arpa.

    python tools/build_bigram_model.py <path to bigram_p50.arpa>

Source (CC BY 4.0, attribution in THIRD_PARTY_NOTICES.txt):
    https://codeberg.org/chewing/libchewing-data
    dict/chewing_v4/bigram_p50.arpa at commit SOURCE_COMMIT
    "chewing: introduce bigrams trained from CC-100"

The ARPA file has no backoff weights: libchewing interpolates instead.  We
keep every bigram it ships (measured: pruning to 20% cost 46 of the 165
selections the full model saves, because the pair that decides a homophone --
我→試 in 我試了一下 -- is exactly the kind a size cut drops).

Output, next to the other generated data (do not hand-edit either):
    bopomofo_core/data/bigram_model.json     metadata, provenance, calibration
    bopomofo_core/data/bigram_model.bin.gz   the tables, see bigram_model.py

The calibration offset maps our own lexicon weights onto the model's scale
for words the model does not have: ln P_model(w) ~= ln(weight(w) + 1) + offset,
fitted as the median over words both know.
"""

from __future__ import annotations

import array
import gzip
import hashlib
import json
import math
import statistics
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "bopomofo_core" / "data"
SOURCE_URL = "https://codeberg.org/chewing/libchewing-data"
SOURCE_PATH = "dict/chewing_v4/bigram_p50.arpa"
SOURCE_COMMIT = "40acb515b420eb0eaeb0186db1113a72cc9f4e94"
SOURCE_SHA256 = "ce25ad7e282cfc710f61eea20ba666b3116ffc37de02f92e2df889fbeb811ee5"
SCALE = 1000  # log10 probabilities are stored as int16 thousandths
MAGIC = b"SPBGRAM1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_arpa(path: Path):
    unigram: dict[str, float] = {}
    bigrams: list[tuple[str, str, float]] = []
    section = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.startswith("\\"):
                section = line
                continue
            if not line:
                continue
            if section == "\\1-grams:":
                logp, word = line.split(" ", 1)
                unigram[word] = float(logp)
            elif section == "\\2-grams:":
                logp, left, right = line.split(" ")
                bigrams.append((left, right, float(logp)))
    return unigram, bigrams


def calibration_offset(unigram: dict[str, float]) -> tuple[float, int]:
    with gzip.open(DATA / "reading_phrases.json.gz", "rt", encoding="utf-8") as handle:
        entries = json.load(handle)["entries"]
    diffs = [
        unigram[phrase] * math.log(10) - math.log(weight + 1)
        for rows in entries.values()
        for phrase, weight in rows
        if phrase in unigram and weight > 0
    ]
    return statistics.median(diffs), len(diffs)


def build(arpa: Path) -> None:
    actual = sha256(arpa)
    if actual != SOURCE_SHA256:
        raise SystemExit(f"{arpa} is not the pinned source: sha256 {actual}")
    unigram, bigrams = read_arpa(arpa)
    words = sorted(unigram)
    ids = {word: index for index, word in enumerate(words)}

    # Group by left word: offsets[left] .. offsets[left + 1] index the sorted
    # right-word ids and their probabilities.
    bigrams.sort(key=lambda item: (ids[item[0]], ids[item[1]]))
    offsets = array.array("I", [0] * (len(words) + 1))
    rights = array.array("I")
    values = array.array("h")
    for left, right, logp in bigrams:
        offsets[ids[left] + 1] += 1
        rights.append(ids[right])
        values.append(int(round(logp * SCALE)))
    for index in range(len(words)):
        offsets[index + 1] += offsets[index]
    uni = array.array("h", (int(round(unigram[word] * SCALE)) for word in words))
    for table in (offsets, rights, values, uni):
        if sys.byteorder != "little":
            table.byteswap()

    word_blob = "\n".join(words).encode("utf-8")
    out = DATA / "bigram_model.bin.gz"
    # mtime=0 so identical input gives byte-identical output.
    with out.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
        handle.write(MAGIC)
        handle.write(struct.pack("<IIII", len(words), len(rights), len(word_blob), SCALE))
        handle.write(word_blob)
        for table in (uni, offsets, rights, values):
            handle.write(table.tobytes())

    offset, samples = calibration_offset(unigram)
    meta = {
        "source": SOURCE_URL,
        "source_path": SOURCE_PATH,
        "source_commit": SOURCE_COMMIT,
        "source_sha256": SOURCE_SHA256,
        "license": "CC-BY-4.0",
        "attribution": "Chewing Chinese Bigram Language Model, libchewing-data (Chewing Project)",
        "modifications": (
            "Converted from ARPA to a compact binary table; log10 probabilities "
            "rounded to 0.001. No entries added or removed."
        ),
        "words": len(words),
        "bigrams": len(rights),
        "lambda": 0.6,
        "oov_offset": round(offset, 4),
        "oov_offset_samples": samples,
        "generator": "tools/build_bigram_model.py",
    }
    (DATA / "bigram_model.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(words):,} words, {len(rights):,} bigrams -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    build(Path(sys.argv[1]))
