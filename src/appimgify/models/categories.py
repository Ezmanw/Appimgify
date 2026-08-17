"""The freedesktop.org main categories offered in the editor.

Only registered main categories are exposed, so every generated desktop entry
validates and every desktop environment knows where to file the launcher.
"""

from __future__ import annotations

#: ``(desktop entry value, human label)`` in menu order.
MAIN_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("AudioVideo", "Multimedia"),
    ("Development", "Development"),
    ("Education", "Education"),
    ("Game", "Games"),
    ("Graphics", "Graphics"),
    ("Network", "Internet"),
    ("Office", "Office"),
    ("Science", "Science"),
    ("Settings", "Settings"),
    ("System", "System"),
    ("Utility", "Utilities"),
)

_LABELS = dict(MAIN_CATEGORIES)
_VALUES = frozenset(_LABELS)


def is_main_category(value: str) -> bool:
    return value in _VALUES


def label_for(value: str) -> str:
    """Human label for a category, falling back to the raw value."""
    return _LABELS.get(value, value)


def describe(values: list[str]) -> str:
    """Comma-joined labels for a list of categories, for list subtitles."""
    if not values:
        return "No categories"
    return ", ".join(label_for(value) for value in values)


def normalise(values: list[str]) -> list[str]:
    """Drop unknown and duplicated entries, keeping menu order."""
    chosen = {value for value in values if value in _VALUES}
    return [value for value, _label in MAIN_CATEGORIES if value in chosen]
