"""Thin wrappers over the standard GTK and Libadwaita dialogs.

Everything here is a stock ``AdwAlertDialog``, ``GtkFileDialog`` or
``AdwToast``; the helpers exist only so error handling reads the same
everywhere and so a raised :class:`AppimgifyError` always reaches the user
with its title and detail intact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from gi.repository import Adw, Gio, GLib, Gtk

from ..utils.errors import AppimgifyError

def present_error(parent: Gtk.Widget, title: str, detail: str = "") -> Adw.AlertDialog:
    """Show a non-recoverable-operation error with a single Close button."""
    dialog = Adw.AlertDialog(heading=title, body=detail or "")
    dialog.add_response("close", "_Close")
    dialog.set_default_response("close")
    dialog.set_close_response("close")
    dialog.present(parent)
    return dialog


def present_exception(parent: Gtk.Widget, error: BaseException) -> Adw.AlertDialog:
    """Show any exception, using its user-facing text when it has some."""
    if isinstance(error, AppimgifyError):
        return present_error(parent, error.title, error.detail)
    if isinstance(error, GLib.Error):
        return present_error(parent, "Something went wrong", error.message)
    return present_error(parent, "Something went wrong", str(error))


def confirm(
    parent: Gtk.Widget,
    heading: str,
    body: str,
    *,
    confirm_label: str,
    on_confirm: Callable[[], None],
    destructive: bool = False,
    extra_child: Gtk.Widget | None = None,
) -> Adw.AlertDialog:
    """Ask a yes/no question, calling ``on_confirm`` only on confirmation."""
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", "_Cancel")
    dialog.add_response("confirm", confirm_label)
    dialog.set_response_appearance(
        "confirm",
        Adw.ResponseAppearance.DESTRUCTIVE
        if destructive
        else Adw.ResponseAppearance.SUGGESTED,
    )
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    if extra_child is not None:
        dialog.set_extra_child(extra_child)

    def responded(_dialog: Adw.AlertDialog, response: str) -> None:
        if response == "confirm":
            on_confirm()

    dialog.connect("response", responded)
    dialog.present(parent)
    return dialog


def choose_response(
    parent: Gtk.Widget,
    heading: str,
    body: str,
    responses: Sequence[tuple[str, str, Adw.ResponseAppearance]],
    on_response: Callable[[str], None],
) -> Adw.AlertDialog:
    """A multi-choice question (used for duplicate handling)."""
    dialog = Adw.AlertDialog(heading=heading, body=body)
    for identifier, label, appearance in responses:
        dialog.add_response(identifier, label)
        dialog.set_response_appearance(identifier, appearance)
    dialog.set_default_response(responses[0][0])
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda _dialog, response: on_response(response))
    dialog.present(parent)
    return dialog


# ----------------------------------------------------------------------
# File choosers
# ----------------------------------------------------------------------
def appimage_filters() -> Gio.ListStore:
    """File filters offering AppImages first, then every file."""
    appimages = Gtk.FileFilter(name="AppImages")
    appimages.add_pattern("*.AppImage")
    appimages.add_pattern("*.appimage")
    appimages.add_mime_type("application/x-iso9660-appimage")
    appimages.add_mime_type("application/vnd.appimage")
    appimages.add_mime_type("application/x-executable")

    everything = Gtk.FileFilter(name="All Files")
    everything.add_pattern("*")

    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(appimages)
    filters.append(everything)
    return filters


def image_filters() -> Gio.ListStore:
    images = Gtk.FileFilter(name="Images")
    for pattern in ("*.png", "*.svg", "*.svgz", "*.xpm", "*.jpg", "*.jpeg", "*.ico"):
        images.add_pattern(pattern)
    images.add_mime_type("image/png")
    images.add_mime_type("image/svg+xml")
    images.add_mime_type("image/jpeg")

    everything = Gtk.FileFilter(name="All Files")
    everything.add_pattern("*")

    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(images)
    filters.append(everything)
    return filters


def open_file(
    parent: Gtk.Window,
    title: str,
    filters: Gio.ListStore,
    on_chosen: Callable[[Path], None],
    *,
    initial_folder: Path | None = None,
) -> None:
    """Open the desktop's standard file chooser (portal-aware)."""
    dialog = Gtk.FileDialog(title=title, modal=True)
    dialog.set_filters(filters)
    dialog.set_default_filter(filters.get_item(0))
    if initial_folder is not None and initial_folder.is_dir():
        dialog.set_initial_folder(Gio.File.new_for_path(str(initial_folder)))

    def finished(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            chosen = source.open_finish(result)
        except GLib.Error:
            return  # the user dismissed the chooser
        if chosen is not None and chosen.get_path():
            on_chosen(Path(chosen.get_path()))

    dialog.open(parent, None, finished)


def select_folder(
    parent: Gtk.Window,
    title: str,
    on_chosen: Callable[[Path], None],
    *,
    initial_folder: Path | None = None,
) -> None:
    dialog = Gtk.FileDialog(title=title, modal=True)
    if initial_folder is not None and initial_folder.is_dir():
        dialog.set_initial_folder(Gio.File.new_for_path(str(initial_folder)))

    def finished(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            chosen = source.select_folder_finish(result)
        except GLib.Error:
            return
        if chosen is not None and chosen.get_path():
            on_chosen(Path(chosen.get_path()))

    dialog.select_folder(parent, None, finished)


def open_in_file_manager(parent: Gtk.Widget, path: Path) -> None:
    """Reveal a file or folder in the user's file manager."""
    root = parent.get_root() if isinstance(parent, Gtk.Widget) else None
    window = root if isinstance(root, Gtk.Window) else None
    launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(str(path)))
    if path.is_dir():
        launcher.launch(window, None, None)
    else:
        launcher.open_containing_folder(window, None, None)
