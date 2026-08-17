"""The ``AdwApplication`` subclass: lifecycle, actions and accelerators."""

from __future__ import annotations

import sys
from pathlib import Path

from gi.repository import Adw, Gio, GLib

from ..services.library_service import LibraryService
from ..ui.preferences import apply_color_scheme
from ..ui.window import MainWindow
from ..utils.errors import AppimgifyError
from ..utils.paths import APP_ID


class AppimgifyApplication(Adw.Application):
    """Appimgify's application object."""

    __gtype_name__ = "AppimgifyApplication"

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._service = LibraryService()
        self._window: MainWindow | None = None

        self.set_option_context_parameter_string("[APPIMAGE…]")
        self.set_option_context_summary(
            "Manage AppImages and their application menu launchers."
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        try:
            self._service.load()
        except AppimgifyError as error:
            print(f"appimgify: {error.title}: {error.detail}", file=sys.stderr)
        apply_color_scheme(self._service.settings.color_scheme)
        self._register_actions()

    def do_activate(self) -> None:
        self._present_window()

    def do_open(self, files: list[Gio.File], _n_files: int, _hint: str) -> None:
        """Handle ``appimgify some.AppImage`` and file-manager “Open With”."""
        window = self._present_window()
        for file in files:
            path = file.get_path()
            if path:
                GLib.idle_add(window.import_path, Path(path))
                break  # one import dialog at a time

    def do_shutdown(self) -> None:
        if self._window is not None:
            self._window.save_state()
        Adw.Application.do_shutdown(self)

    def _present_window(self) -> MainWindow:
        if self._window is None:
            self._window = MainWindow(self, self._service)
            self._window.connect("close-request", self._on_close_request)
        self._window.present()
        return self._window

    def _on_close_request(self, window: MainWindow) -> bool:
        window.save_state()
        return False

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _register_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda _action, _param: self.quit())
        self.add_action(quit_action)

        accelerators = {
            "app.quit": ["<Control>q"],
            "win.add-appimage": ["<Control>n"],
            "win.search": ["<Control>f"],
            "win.preferences": ["<Control>comma"],
            "win.shortcuts": ["<Control>question"],
            "window.close": ["<Control>w"],
        }
        for action, keys in accelerators.items():
            self.set_accels_for_action(action, keys)


def main(argv: list[str] | None = None) -> int:
    """Entry point used by the installed launcher script."""
    Adw.init()
    application = AppimgifyApplication()
    return application.run(argv if argv is not None else sys.argv)


__all__ = ["AppimgifyApplication", "main"]
