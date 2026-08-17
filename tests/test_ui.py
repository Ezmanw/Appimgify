"""Smoke tests for the interface layer.

Widget construction needs a display, so those tests skip automatically on a
headless machine (CI, a build server). The pure functions in the UI layer are
always tested.
"""

from __future__ import annotations

import unittest
import uuid

from helpers import TempDirTestCase

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from appimgify.persistence.config import SettingsStore
from appimgify.persistence.library import Library
from appimgify.persistence.presets_store import PresetStore
from appimgify.services.library_service import LibraryService
from appimgify.ui.app_row import escape_markup


def display_available() -> bool:
    """True when a display is present, so widgets can actually be built."""
    try:
        return bool(Gtk.init_check())
    except Exception:
        return False


class MarkupTests(unittest.TestCase):
    def test_ampersands_are_escaped_for_pango(self) -> None:
        self.assertEqual(escape_markup("Rock & Roll"), "Rock &amp; Roll")

    def test_angle_brackets_cannot_inject_markup(self) -> None:
        self.assertEqual(
            escape_markup("<b>bold</b>"), "&lt;b&gt;bold&lt;/b&gt;"
        )

    def test_plain_names_are_unchanged(self) -> None:
        self.assertEqual(escape_markup("Simple Name"), "Simple Name")


@unittest.skipUnless(display_available(), "no display available")
class WidgetTests(TempDirTestCase):
    """Builds the real widgets to catch construction and API mistakes."""

    def setUp(self) -> None:
        super().setUp()
        Adw.init()
        self.service = LibraryService(SettingsStore(), Library(), PresetStore())
        self.service.load()

    def build_window(self):
        from appimgify.ui.window import MainWindow

        # A distinct id per test: registering the same one twice in one
        # process collides on the session bus.
        application = Adw.Application(
            application_id=f"io.github.ezmanw.AppimgifyTest{uuid.uuid4().hex[:8]}"
        )
        application.register()  # windows may only be added after registration
        window = MainWindow(application, self.service)
        self.addCleanup(window.destroy)
        return window

    def pump(self, milliseconds: int = 400) -> None:
        """Run the main loop briefly so delayed signals (search) fire."""
        deadline = GLib.get_monotonic_time() + milliseconds * 1000
        context = GLib.MainContext.default()
        while GLib.get_monotonic_time() < deadline:
            if not context.iteration(False):
                GLib.usleep(5000)

    def import_appimage(self, file_name: str = "Example.AppImage", **overrides):
        draft = self.service.prepare_import(self.make_appimage(file_name))
        app = draft.app.copy_with(**overrides) if overrides else draft.app
        return self.service.commit_import(draft, app)

    def test_the_main_window_builds(self) -> None:
        window = self.build_window()
        self.assertEqual(window.get_title(), "Appimgify")

    def test_an_imported_application_appears_in_the_list(self) -> None:
        app = self.import_appimage("Krita-5.2.2-x86_64.AppImage")
        window = self.build_window()

        self.assertIn(app.id, window._rows)
        row = window._rows[app.id]
        self.assertEqual(row.get_title(), "Krita")

    def test_selecting_an_application_shows_it_in_the_detail_pane(self) -> None:
        app = self.import_appimage("Krita-5.2.2-x86_64.AppImage")
        window = self.build_window()

        detail = window._detail
        self.assertIsNotNone(detail.app)
        assert detail.app is not None
        self.assertEqual(detail.app.id, app.id)
        self.assertFalse(detail.has_unsaved_changes)

    def test_searching_filters_the_list(self) -> None:
        self.import_appimage("Krita.AppImage", name="Krita")
        self.import_appimage("Inkscape.AppImage", name="Inkscape")
        window = self.build_window()

        window._search_entry.set_text("krit")
        self.pump()
        self.assertEqual([row.get_title() for row in window._rows.values()], ["Krita"])

        window._search_entry.set_text("")
        self.pump()
        self.assertEqual(len(window._rows), 2)

    def test_the_editor_round_trips_an_application(self) -> None:
        from appimgify.models.managed_app import ManagedApp
        from appimgify.ui.editor import AppEditor

        app = ManagedApp(
            name="Example",
            appimage_path="/tmp/Example.AppImage",
            categories=["Game"],
            arguments=["--flag", "two words"],
            description="Fun",
        )
        editor = AppEditor()
        editor.load(app, presets=self.service.presets())
        collected = editor.collect()

        self.assertEqual(collected.name, "Example")
        self.assertEqual(collected.categories, ["Game"])
        self.assertEqual(collected.arguments, ["--flag", "two words"])
        self.assertEqual(collected.description, "Fun")

    def test_the_editor_rejects_an_empty_name(self) -> None:
        from appimgify.models.managed_app import ManagedApp
        from appimgify.ui.editor import AppEditor

        editor = AppEditor()
        editor.load(ManagedApp(name="X", appimage_path="/tmp/X.AppImage"))
        editor._name_row.set_text("   ")
        with self.assertRaises(ValueError):
            editor.collect()

    def test_the_preferences_window_builds(self) -> None:
        from appimgify.ui.preferences import PreferencesWindow

        window = PreferencesWindow(self.service)
        self.assertIsInstance(window, Adw.PreferencesWindow)
        window.destroy()


if __name__ == "__main__":
    unittest.main()
