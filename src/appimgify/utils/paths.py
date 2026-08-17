"""XDG base-directory helpers.

Every path the application touches is derived from these helpers so that the
whole program can be redirected (in tests, or through the ``XDG_*`` variables)
without touching the real user profile.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

APP_ID = "io.github.ezmanw.Appimgify"
APP_DIR_NAME = "appimgify"


def _env_dir(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    if value:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
    return fallback


def home() -> Path:
    return Path(os.path.expanduser("~"))


def xdg_config_home() -> Path:
    return _env_dir("XDG_CONFIG_HOME", home() / ".config")


def xdg_data_home() -> Path:
    return _env_dir("XDG_DATA_HOME", home() / ".local" / "share")


def xdg_cache_home() -> Path:
    return _env_dir("XDG_CACHE_HOME", home() / ".cache")


def config_dir() -> Path:
    """Directory holding user preferences (``~/.config/appimgify``)."""
    return xdg_config_home() / APP_DIR_NAME


def data_dir() -> Path:
    """Directory holding the application library (``~/.local/share/appimgify``)."""
    return xdg_data_home() / APP_DIR_NAME


def default_appimage_dir() -> Path:
    """Default managed AppImage store (``~/.local/share/appimages``)."""
    return xdg_data_home() / "appimages"


def default_launcher_dir() -> Path:
    """User-local desktop-entry directory (``~/.local/share/applications``)."""
    return xdg_data_home() / "applications"


def default_icon_dir() -> Path:
    """User-local icon theme root (``~/.local/share/icons``)."""
    return xdg_data_home() / "icons"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def contract_user(path: Path | str) -> str:
    """Render ``path`` with ``~`` for display, without ever guessing."""
    text = str(path)
    home_text = str(home())
    if text == home_text:
        return "~"
    if text.startswith(home_text + os.sep):
        return "~" + text[len(home_text) :]
    return text


def expand_user(text: str) -> Path:
    return Path(os.path.expanduser(text.strip()))


_SLUG_STRIP = re.compile(r"[^A-Za-z0-9._-]+")
_SLUG_COLLAPSE = re.compile(r"-{2,}")


def slugify(name: str, fallback: str = "appimage") -> str:
    """Turn a display name into a safe single path component.

    The result never contains a path separator, never starts with a dot and is
    always non-empty, which makes it safe to join onto a managed directory.
    """
    normalised = unicodedata.normalize("NFKD", name)
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_text).strip("-._")
    slug = _SLUG_COLLAPSE.sub("-", slug)
    if not slug:
        return fallback
    return slug[:96]


def unique_path(parent: Path, stem: str, suffix: str = "") -> Path:
    """Return a path inside ``parent`` that does not exist yet.

    ``stem`` is suffixed with ``-2``, ``-3``… until the name is free.  Used for
    never-overwrite semantics on import.
    """
    candidate = parent / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def is_within(path: Path, parent: Path) -> bool:
    """True when ``path`` lives inside ``parent`` (both resolved leniently)."""
    try:
        resolved = Path(os.path.abspath(str(path)))
        base = Path(os.path.abspath(str(parent)))
        return resolved == base or base in resolved.parents
    except OSError:
        return False
