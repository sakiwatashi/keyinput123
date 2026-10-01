"""Word-bigram language model for the sentence lattice.

The lexicon knows how common each word is on its own, not what follows what,
so 我試了一下 came out as 我是了一下: 是 is 35 times more common than 試. The
model knows that 了 after 是 is a hundred times rarer than usual and after 試
four times more likely. This module answers those two questions cheaply.

Data: libchewing-data's bigram model (CC BY 4.0), converted by
tools/build_bigram_model.py into bigram_model.bin.gz. Never hand-edit it.

Memory matters: PIME runs one Python server for every application. Bigrams
are stored grouped by left word -- an offset table into sorted right-word ids
and int16 probabilities -- about 6 bytes each, instead of a dict entry each.

Everything here fails soft. A missing or damaged file means no model, and the
lattice falls back to its frequency-only scoring.
"""

from __future__ import annotations

import array
import bisect
import gzip
import json
import math
import struct
import sys
from pathlib import Path

DATA = Path(__file__).with_name("data")
MODEL_PATH = DATA / "bigram_model.bin.gz"
META_PATH = DATA / "bigram_model.json"
MAGIC = b"SPBGRAM1"
LN10 = math.log(10)


class BigramModel:
    """Read-only word unigram/bigram tables in natural-log units."""

    def __init__(self, path: Path = MODEL_PATH, meta_path: Path = META_PATH) -> None:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        self.lam = float(meta["lambda"])
        self.oov_offset = float(meta["oov_offset"])
        with gzip.open(path, "rb") as handle:
            blob = handle.read()
        if blob[: len(MAGIC)] != MAGIC:
            raise ValueError("not a bigram model file")
        position = len(MAGIC)
        words, bigrams, word_bytes, scale = struct.unpack_from("<IIII", blob, position)
        position += 16
        self.scale = float(scale)
        vocabulary = blob[position : position + word_bytes].decode("utf-8").split("\n")
        position += word_bytes
        if len(vocabulary) != words:
            raise ValueError("vocabulary size mismatch")
        self.ids = {word: index for index, word in enumerate(vocabulary)}

        def take(typecode: str, count: int) -> array.array:
            nonlocal position
            table = array.array(typecode)
            size = table.itemsize * count
            table.frombytes(blob[position : position + size])
            position += size
            if sys.byteorder != "little":
                table.byteswap()
            return table

        self.unigram = take("h", words)
        self.offsets = take("I", words + 1)
        self.rights = take("I", bigrams)
        self.values = take("h", bigrams)
        if position != len(blob):
            raise ValueError("trailing or missing bytes in the bigram model")
        self.log_floor = math.log(1 - self.lam)

    def knows(self, word: str) -> bool:
        return word in self.ids

    def unigram_ln(self, word: str) -> float | None:
        index = self.ids.get(word)
        if index is None:
            return None
        return self.unigram[index] / self.scale * LN10

    def bigram_ln(self, previous: str, word: str) -> float | None:
        """ln P(word | previous) as stored, or None when the pair is not stored."""
        left = self.ids.get(previous)
        right = self.ids.get(word)
        if left is None or right is None:
            return None
        start, end = self.offsets[left], self.offsets[left + 1]
        position = bisect.bisect_left(self.rights, right, start, end)
        if position < end and self.rights[position] == right:
            return self.values[position] / self.scale * LN10
        return None


_SHARED: BigramModel | None = None
_LOADED = False


def shared_model() -> BigramModel | None:
    """One copy per process; several text-service instances share it."""
    global _SHARED, _LOADED
    if not _LOADED:
        _LOADED = True
        try:
            # Read the module globals at call time so a test can point them
            # at a damaged file.
            _SHARED = BigramModel(MODEL_PATH, META_PATH)
        except (OSError, ValueError, KeyError, struct.error):
            # No model is a supported configuration, not a failure to start.
            _SHARED = None
    return _SHARED
