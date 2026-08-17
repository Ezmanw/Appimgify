"""The application's central data model.

A :class:`ManagedApp` is the single source of truth for one imported AppImage.
The generated ``.desktop`` file is treated as *output*: it can be deleted or
edited by anything on the system and Appimgify can always regenerate it from
this record.
"""

from __future__ import annotations

import shlex
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from . import categories as categories_module

#: Bumped when the on-disk shape changes; readers migrate forward.
LIBRARY_SCHEMA_VERSION = 1


def _new_id() -> str:
    return uuid.uuid4().hex


def _as_str(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default


def _as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


@dataclass
class ManagedApp:
    """One AppImage under management, plus its launcher configuration."""

    name: str
    appimage_path: str
    id: str = field(default_factory=_new_id)
    generic_name: str = ""
    description: str = ""
    version: str = ""
    icon_path: str = ""
    categories: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    working_directory: str = ""
    terminal: bool = False
    startup_notify: bool = True
    single_main_window: bool = False
    keywords: list[str] = field(default_factory=list)
    mime_types: list[str] = field(default_factory=list)
    no_display: bool = False
    desktop_entry_path: str = ""
    desktop_file_name: str = ""
    source_path: str = ""
    imported_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    @property
    def appimage(self) -> Path:
        return Path(self.appimage_path)

    @property
    def icon(self) -> Path | None:
        return Path(self.icon_path) if self.icon_path else None

    @property
    def desktop_entry(self) -> Path | None:
        return Path(self.desktop_entry_path) if self.desktop_entry_path else None

    @property
    def storage_dir(self) -> Path:
        return self.appimage.parent

    @property
    def appimage_filename(self) -> str:
        return self.appimage.name

    def appimage_exists(self) -> bool:
        return bool(self.appimage_path) and self.appimage.is_file()

    def icon_exists(self) -> bool:
        return bool(self.icon_path) and Path(self.icon_path).is_file()

    def launcher_exists(self) -> bool:
        return bool(self.desktop_entry_path) and Path(self.desktop_entry_path).is_file()

    @property
    def arguments_text(self) -> str:
        """Arguments rendered as a shell-style string for entry fields."""
        return " ".join(shlex.quote(argument) for argument in self.arguments)

    def display_subtitle(self) -> str:
        """Short line used under the name in the library list."""
        parts = [part for part in (self.description, self.version) if part]
        return " · ".join(parts) if parts else self.appimage_filename

    def matches(self, needle: str) -> bool:
        """Case-insensitive search across the fields a user would type."""
        query = needle.strip().casefold()
        if not query:
            return True
        haystack = " ".join(
            [
                self.name,
                self.generic_name,
                self.description,
                self.version,
                self.appimage_filename,
                " ".join(self.keywords),
                " ".join(
                    categories_module.label_for(value) for value in self.categories
                ),
            ]
        ).casefold()
        return query in haystack

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "generic_name": self.generic_name,
            "description": self.description,
            "version": self.version,
            "appimage_path": self.appimage_path,
            "icon_path": self.icon_path,
            "categories": list(self.categories),
            "arguments": list(self.arguments),
            "working_directory": self.working_directory,
            "terminal": self.terminal,
            "startup_notify": self.startup_notify,
            "single_main_window": self.single_main_window,
            "keywords": list(self.keywords),
            "mime_types": list(self.mime_types),
            "no_display": self.no_display,
            "desktop_entry_path": self.desktop_entry_path,
            "desktop_file_name": self.desktop_file_name,
            "source_path": self.source_path,
            "imported_at": self.imported_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "ManagedApp | None":
        """Rebuild an app from JSON, returning ``None`` for unusable records.

        Anything missing is defaulted rather than raising: one damaged entry
        must never prevent the rest of the library from loading.
        """
        if not isinstance(payload, dict):
            return None
        name = _as_str(payload.get("name"))
        appimage_path = _as_str(payload.get("appimage_path"))
        if not name or not appimage_path:
            return None
        now = time.time()
        return cls(
            id=_as_str(payload.get("id")) or _new_id(),
            name=name,
            generic_name=_as_str(payload.get("generic_name")),
            description=_as_str(payload.get("description")),
            version=_as_str(payload.get("version")),
            appimage_path=appimage_path,
            icon_path=_as_str(payload.get("icon_path")),
            categories=categories_module.normalise(
                _as_str_list(payload.get("categories"))
            ),
            arguments=_as_str_list(payload.get("arguments")),
            working_directory=_as_str(payload.get("working_directory")),
            terminal=_as_bool(payload.get("terminal"), False),
            startup_notify=_as_bool(payload.get("startup_notify"), True),
            single_main_window=_as_bool(payload.get("single_main_window"), False),
            keywords=_as_str_list(payload.get("keywords")),
            mime_types=_as_str_list(payload.get("mime_types")),
            no_display=_as_bool(payload.get("no_display"), False),
            desktop_entry_path=_as_str(payload.get("desktop_entry_path")),
            desktop_file_name=_as_str(payload.get("desktop_file_name")),
            source_path=_as_str(payload.get("source_path")),
            imported_at=_as_float(payload.get("imported_at"), now),
            updated_at=_as_float(payload.get("updated_at"), now),
        )

    def copy_with(self, **changes: Any) -> "ManagedApp":
        """Return a modified copy, refreshing ``updated_at``."""
        changes.setdefault("updated_at", time.time())
        return replace(self, **changes)


def _as_float(value: Any, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default
