"""Microsoft-Bopomofo-like single-syllable editing core."""

from .state import BopomofoEditor, Event, EventKind

__all__ = ["BopomofoEditor", "Event", "EventKind"]
