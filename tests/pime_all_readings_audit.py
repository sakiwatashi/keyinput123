"""Exhaustively audit single-syllable Bopomofo defaults with PIME's Python.

This is intentionally separate from normal 64-bit unit tests because the
bundled libchewing DLL is 32-bit. It enumerates every initial/medial/rime/tone
slot combination, lets libchewing decide which readings exist, and verifies
that global character frequency never displaces the reading-aware default.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIME_ROOT = Path(os.environ.get("PIME_ROOT", r"C:\Program Files (x86)\PIME"))
sys.path.insert(0, str(PIME_ROOT / "python"))
sys.path.insert(
    0,
    str(PROJECT_ROOT / "dist" / "PIME-overlay" / "python" / "input_methods"),
)

from pinned_bopomofo import pinned_libchewing
from pinned_bopomofo.bopomofo_core.keymap import keys_for_reading
from pinned_bopomofo.bopomofo_core.libchewing_provider import (
    MAX_CANDIDATES,
    TAIWAN_FREQUENCY,
    LibChewingProvider,
    prioritize_common_character,
)
from pinned_bopomofo.bopomofo_core.state import INITIALS, MEDIALS, RIMES, TONES


def raw_candidates(provider: LibChewingProvider, reading: str) -> list[str]:
    context = provider.context
    context.Reset()
    for key in keys_for_reading(reading):
        context.handle_Default(ord(key))
    if context.cand_TotalChoice() <= 0:
        return []
    context.cand_Enumerate()
    results: list[str] = []
    while context.cand_hasNext() and len(results) < MAX_CANDIDATES:
        candidate = context.cand_String().decode("utf-8")
        if candidate not in results:
            results.append(candidate)
    return results


def completed_readings():
    initials = ("",) + tuple(sorted(INITIALS))
    medials = ("",) + tuple(sorted(MEDIALS))
    rimes = ("",) + tuple(sorted(RIMES))
    tones = tuple(sorted(TONES))
    for initial, medial, rime, tone in itertools.product(
        initials, medials, rimes, tones
    ):
        body = initial + medial + rime
        if body:
            yield body + tone


def audit_all_readings() -> dict[str, object]:
    provider = LibChewingProvider(pinned_libchewing)
    total = 0
    valid = 0
    audited_characters: set[str] = set()
    old_frequency_promotions: list[dict[str, str]] = []
    errors: list[str] = []

    for reading in completed_readings():
        total += 1
        raw = raw_candidates(provider, reading)
        if not raw:
            continue
        valid += 1
        audited_characters.update(
            candidate for candidate in raw if len(candidate) == 1
        )

        preserved = TAIWAN_FREQUENCY.rank_characters(
            raw, preserve_first=True
        )
        expected = prioritize_common_character(reading, preserved)
        final = provider.candidates(reading)
        if not expected or not final:
            errors.append(f"{reading!r}: dictionary candidates disappeared")
            continue
        if final[0] != expected[0]:
            errors.append(
                f"{reading!r}: expected {expected[0]!r}, got {final[0]!r}"
            )
        if raw[0] not in final:
            errors.append(
                f"{reading!r}: raw default {raw[0]!r} missing from final list"
            )
        if len(final) != len(dict.fromkeys(final)):
            errors.append(f"{reading!r}: duplicate final candidates")
        literal = reading[:-1] if reading.endswith("ˉ") else reading
        if literal not in final[:4]:
            errors.append(f"{reading!r}: literal spelling is not in first four")

        old_ranked = prioritize_common_character(
            reading, TAIWAN_FREQUENCY.rank_characters(raw)
        )
        if old_ranked and old_ranked[0] != expected[0]:
            old_frequency_promotions.append(
                {
                    "reading": reading,
                    "dictionary": expected[0],
                    "old_global_frequency": old_ranked[0],
                }
            )

    summary = {
        "generated_combinations": total,
        "dictionary_readings": valid,
        "distinct_characters_audited": len(audited_characters),
        "old_global_frequency_promotions_blocked": len(
            old_frequency_promotions
        ),
        "promotion_examples": old_frequency_promotions[:20],
        "errors": errors[:50],
    }
    return summary


def main() -> None:
    summary = audit_all_readings()
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    errors = summary["errors"]
    if errors:
        raise AssertionError(f"all-reading audit found {len(errors)} errors")


if __name__ == "__main__":
    main()
