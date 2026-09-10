"""Small, crash-safe helpers for the IME's JSON user data."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, preserving an unreadable file for recovery."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("the root JSON value must be an object")
        return raw
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        _preserve_corrupt_file(path)
        return {}


def save_json_object(
    path: Path, value: dict[str, Any], sort_keys: bool = False
) -> None:
    """Atomically replace a JSON file so a crash cannot leave half a write.

    ``sort_keys`` is off by default because the live stores lean on insertion
    order: PhraseStore evicts the oldest entry when it hits its cap, and
    sorting would quietly turn that into "evict whatever sorts first". Sync
    turns it on, where the opposite matters -- two machines that merged to the
    same content must produce byte-identical files, or every sync shows up as a
    change in the shared folder's git history and defeats the backup tool's
    fingerprint check.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=sort_keys)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _preserve_corrupt_file(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    try:
        os.replace(path, backup)
    except OSError:
        # A locked file must not prevent the input method from starting.
        pass
