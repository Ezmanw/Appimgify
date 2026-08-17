"""User preferences, stored as readable JSON.

Kept in ``~/.config/appimgify/settings.json`` rather than in GSettings so the
whole configuration is inspectable and editable by hand, and so the
application has no schema to install before it can run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.fileutils import read_json, write_json
from ..utils.paths import (
    config_dir,
    default_appimage_dir,
    default_launcher_dir,
    expand_user,
)

SETTINGS_SCHEMA_VERSION = 1
SETTINGS_FILE_NAME = "settings.json"

#: Values accepted for the appearance preference.
COLOR_SCHEMES = ("system", "light", "dark")

#: What to do when an import matches an existing application.
DUPLICATE_ACTIONS = ("ask", "import-anyway", "replace")


@dataclass
class Settings:
    """Everything the user can change in Preferences."""

    appimage_dir: str = ""
    launcher_dir: str = ""
    color_scheme: str = "system"
    create_launcher_on_import: bool = True
    extract_icon_on_import: bool = True
    duplicate_action: str = "ask"
    launch_after_import: bool = False
    confirm_removal: bool = True
    sort_order: str = "name"
    window_width: int = 1000
    window_height: int = 700
    window_maximized: bool = False

    # ------------------------------------------------------------------
    @property
    def appimage_path(self) -> Path:
        return expand_user(self.appimage_dir) if self.appimage_dir else default_appimage_dir()

    @property
    def launcher_path(self) -> Path:
        return expand_user(self.launcher_dir) if self.launcher_dir else default_launcher_dir()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "appimage_dir": self.appimage_dir,
            "launcher_dir": self.launcher_dir,
            "color_scheme": self.color_scheme,
            "create_launcher_on_import": self.create_launcher_on_import,
            "extract_icon_on_import": self.extract_icon_on_import,
            "duplicate_action": self.duplicate_action,
            "launch_after_import": self.launch_after_import,
            "confirm_removal": self.confirm_removal,
            "sort_order": self.sort_order,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "window_maximized": self.window_maximized,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "Settings":
        """Build settings from JSON, ignoring anything unrecognised.

        A partially corrupted settings file therefore degrades to defaults for
        the affected keys instead of preventing start-up.
        """
        settings = cls()
        if not isinstance(payload, dict):
            return settings

        def text(key: str, default: str, allowed: tuple[str, ...] | None = None) -> str:
            value = payload.get(key)
            if not isinstance(value, str):
                return default
            value = value.strip()
            if allowed is not None and value not in allowed:
                return default
            return value

        def flag(key: str, default: bool) -> bool:
            value = payload.get(key)
            return value if isinstance(value, bool) else default

        def number(key: str, default: int, minimum: int) -> int:
            value = payload.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return default
            return max(minimum, int(value))

        settings.appimage_dir = text("appimage_dir", "")
        settings.launcher_dir = text("launcher_dir", "")
        settings.color_scheme = text("color_scheme", "system", COLOR_SCHEMES)
        settings.create_launcher_on_import = flag("create_launcher_on_import", True)
        settings.extract_icon_on_import = flag("extract_icon_on_import", True)
        settings.duplicate_action = text("duplicate_action", "ask", DUPLICATE_ACTIONS)
        settings.launch_after_import = flag("launch_after_import", False)
        settings.confirm_removal = flag("confirm_removal", True)
        settings.sort_order = text("sort_order", "name", ("name", "recent", "category"))
        settings.window_width = number("window_width", 1000, 360)
        settings.window_height = number("window_height", 700, 294)
        settings.window_maximized = flag("window_maximized", False)
        return settings


class SettingsStore:
    """Loads and saves :class:`Settings`, tolerating a damaged file."""

    def __init__(self, directory: Path | None = None) -> None:
        self._path = Path(directory or config_dir()) / SETTINGS_FILE_NAME
        self._settings = Settings()
        self._recovered = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def recovered_from_corruption(self) -> bool:
        """True when the previous settings file had to be replaced."""
        return self._recovered

    def load(self) -> Settings:
        existed = self._path.exists()
        payload = read_json(self._path, default=None)
        self._recovered = existed and payload is None
        self._settings = Settings.from_dict(payload)
        return self._settings

    def save(self, settings: Settings | None = None) -> None:
        if settings is not None:
            self._settings = settings
        write_json(self._path, self._settings.to_dict())
