"""Result type for AppImage metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedMetadata:
    """What could be read out of an AppImage — every field is optional."""

    name: str = ""
    generic_name: str = ""
    comment: str = ""
    version: str = ""
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    mime_types: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    terminal: bool = False
    startup_notify: bool = True
    icon_name: str = ""
    #: Icon file inside the extraction scratch directory, if one was found.
    icon_source: Path | None = None
    #: Human-readable notes about what could *not* be read.
    notes: list[str] = field(default_factory=list)

    @property
    def has_desktop_entry(self) -> bool:
        return bool(self.name or self.categories or self.comment)

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)
