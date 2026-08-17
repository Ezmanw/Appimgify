"""Displaying application icons with stock widgets only.

No artwork is ever generated. When an AppImage has no icon the standard
``application-x-executable`` icon from the system theme is shown, exactly as a
file manager would do.
"""

from __future__ import annotations

from pathlib import Path

from gi.repository import Gio, Gtk

#: System theme icon used whenever an application has no icon of its own.
FALLBACK_ICON_NAME = "application-x-executable"

#: System theme icon used when an icon file is recorded but missing.
BROKEN_ICON_NAME = "image-missing-symbolic"


def icon_image(path: Path | None, pixel_size: int) -> Gtk.Image:
    """A ``GtkImage`` for an icon file, falling back to the system theme."""
    image = Gtk.Image()
    image.set_pixel_size(pixel_size)
    apply_icon(image, path)
    return image


def apply_icon(image: Gtk.Image, path: Path | None) -> None:
    """Point an existing ``GtkImage`` at an icon file, or at the fallback."""
    if path is not None and path.is_file():
        image.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(str(path))))
    else:
        image.set_from_icon_name(FALLBACK_ICON_NAME)


def status_icon(icon_name: str, pixel_size: int = 16) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(pixel_size)
    return image
