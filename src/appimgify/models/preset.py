"""Reusable launcher configuration presets.

A preset carries launcher *settings* only — never an AppImage — so it can be
applied to any imported application.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from . import categories as categories_module
from .managed_app import ManagedApp

PRESETS_SCHEMA_VERSION = 1


@dataclass
class Preset:
    """A named bundle of desktop-entry settings."""

    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    categories: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    working_directory: str = ""
    terminal: bool = False
    startup_notify: bool = True
    keywords: list[str] = field(default_factory=list)
    builtin: bool = False

    def summary(self) -> str:
        parts = [categories_module.describe(self.categories)]
        if self.terminal:
            parts.append("Runs in a terminal")
        if self.arguments:
            parts.append(" ".join(self.arguments))
        return " · ".join(parts)

    def apply_to(self, app: ManagedApp) -> ManagedApp:
        """Return ``app`` with this preset's settings applied."""
        merged_keywords = list(
            dict.fromkeys([*app.keywords, *self.keywords])
        )
        return app.copy_with(
            categories=list(self.categories),
            arguments=list(self.arguments),
            working_directory=self.working_directory,
            terminal=self.terminal,
            startup_notify=self.startup_notify,
            keywords=merged_keywords,
        )

    @classmethod
    def from_app(cls, name: str, app: ManagedApp) -> "Preset":
        """Capture the launcher settings of an existing application."""
        return cls(
            name=name,
            categories=list(app.categories),
            arguments=list(app.arguments),
            working_directory=app.working_directory,
            terminal=app.terminal,
            startup_notify=app.startup_notify,
            keywords=list(app.keywords),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "categories": list(self.categories),
            "arguments": list(self.arguments),
            "working_directory": self.working_directory,
            "terminal": self.terminal,
            "startup_notify": self.startup_notify,
            "keywords": list(self.keywords),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "Preset | None":
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        def strings(key: str) -> list[str]:
            value = payload.get(key)
            if not isinstance(value, list):
                return []
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]

        identifier = payload.get("id")
        return cls(
            id=identifier if isinstance(identifier, str) and identifier else uuid.uuid4().hex,
            name=name.strip(),
            categories=categories_module.normalise(strings("categories")),
            arguments=strings("arguments"),
            working_directory=payload.get("working_directory", "")
            if isinstance(payload.get("working_directory"), str)
            else "",
            terminal=bool(payload.get("terminal", False)),
            startup_notify=bool(payload.get("startup_notify", True)),
            keywords=strings("keywords"),
        )


def builtin_presets() -> list[Preset]:
    """Presets shipped with the application as sensible starting points."""
    return [
        Preset(
            id="builtin-game",
            name="Gaming App",
            categories=["Game"],
            terminal=False,
            startup_notify=True,
            builtin=True,
        ),
        Preset(
            id="builtin-development",
            name="Development Tool",
            categories=["Development"],
            terminal=False,
            startup_notify=True,
            builtin=True,
        ),
        Preset(
            id="builtin-multimedia",
            name="Multimedia App",
            categories=["AudioVideo"],
            terminal=False,
            startup_notify=True,
            builtin=True,
        ),
        Preset(
            id="builtin-utility",
            name="Utility",
            categories=["Utility"],
            terminal=False,
            startup_notify=True,
            builtin=True,
        ),
    ]
