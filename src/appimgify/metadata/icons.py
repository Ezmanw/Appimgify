"""Storing an application's icon next to its AppImage.

Icons are never generated. They are only ever copied — from inside the
AppImage, or from a file the user picked — and if neither is available the
application simply has no icon and the desktop environment falls back to its
own generic one.
"""

from __future__ import annotations

from pathlib import Path

from ..utils.errors import StorageError
from ..utils.fileutils import copy_file, remove_tree

#: Image formats a desktop environment can be relied upon to render.
SUPPORTED_SUFFIXES = (".png", ".svg", ".svgz", ".xpm", ".jpg", ".jpeg", ".ico")

_MAGIC_BYTES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x1f\x8b", ".svgz"),
    (b"/* XPM */", ".xpm"),
    (b"\x00\x00\x01\x00", ".ico"),
)

#: Base name used for the stored icon, so rebuilds are idempotent.
ICON_STEM = "icon"


def is_supported_image(path: Path) -> bool:
    """True when ``path`` looks like an image a launcher can use."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with open(path, "rb") as stream:
            head = stream.read(512)
    except OSError:
        return False
    if any(head.startswith(magic) for magic, _suffix in _MAGIC_BYTES):
        return True
    if b"<svg" in head or b"<?xml" in head:
        return True
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def detect_suffix(path: Path) -> str:
    """Best file extension for ``path``, sniffed rather than trusted."""
    try:
        with open(path, "rb") as stream:
            head = stream.read(512)
    except OSError:
        head = b""
    for magic, suffix in _MAGIC_BYTES:
        if head.startswith(magic):
            return suffix
    if b"<svg" in head:
        return ".svg"
    suffix = path.suffix.lower()
    return suffix if suffix in SUPPORTED_SUFFIXES else ".png"


def install(source: Path, target_dir: Path) -> Path:
    """Copy ``source`` into ``target_dir`` as the application's icon.

    Any icon previously stored there is replaced, so an application never
    accumulates ``icon.png``/``icon.svg`` duplicates that could disagree.

    Raises:
        StorageError: if the icon cannot be read or written.
    """
    source = Path(source)
    if not is_supported_image(source):
        raise StorageError(
            "Icon could not be used",
            f"“{source.name}” is not an image format that desktop launchers support.",
        )
    suffix = detect_suffix(source)
    target = Path(target_dir) / f"{ICON_STEM}{suffix}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for existing in stored_icons(target_dir):
            if existing != target:
                remove_tree(existing)
        copy_file(source, target)
    except OSError as error:
        raise StorageError(
            "Icon could not be saved",
            f"Copying the icon into “{target_dir}” failed: {error.strerror or error}.",
        ) from error
    return target


def stored_icons(target_dir: Path) -> list[Path]:
    """Icon files Appimgify has stored in an application's directory."""
    if not target_dir.is_dir():
        return []
    return [
        target_dir / f"{ICON_STEM}{suffix}"
        for suffix in SUPPORTED_SUFFIXES
        if (target_dir / f"{ICON_STEM}{suffix}").is_file()
    ]
