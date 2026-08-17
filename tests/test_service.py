"""Tests for the library service — the layer the interface drives.

These exercise the same code paths the widgets use, without a display.
"""

from __future__ import annotations

import os
import unittest

from helpers import TempDirTestCase

from appimgify.persistence.config import SettingsStore
from appimgify.persistence.library import Library
from appimgify.persistence.presets_store import PresetStore
from appimgify.services.library_service import Health, LibraryService, RemovalOptions


class ServiceTestCase(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service = LibraryService(SettingsStore(), Library(), PresetStore())
        self.service.load()

    def import_appimage(self, file_name: str = "Example.AppImage", **overrides):
        draft = self.service.prepare_import(self.make_appimage(file_name))
        app = draft.app.copy_with(**overrides) if overrides else draft.app
        result = self.service.commit_import(draft, app)
        self.service.notify_library_changed()
        return result


class LifecycleTests(ServiceTestCase):
    def test_a_fresh_profile_starts_empty(self) -> None:
        self.assertEqual(self.service.apps, [])
        self.assertEqual(self.service.problems(), [])

    def test_importing_adds_the_application_to_the_library(self) -> None:
        app = self.import_appimage()
        self.assertEqual([item.id for item in self.service.apps], [app.id])
        self.assertIsNotNone(self.service.get(app.id))

    def test_the_library_survives_a_restart(self) -> None:
        app = self.import_appimage()
        reopened = LibraryService(SettingsStore(), Library(), PresetStore())
        reopened.load()
        restored = reopened.get(app.id)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.name, app.name)

    def test_settings_changes_move_where_new_imports_land(self) -> None:
        settings = self.service.settings
        settings.appimage_dir = str(self.root / "custom-store")
        self.service.update_settings(settings)
        app = self.import_appimage()
        self.assertTrue(str(app.appimage_path).startswith(str(self.root / "custom-store")))


class HealthTests(ServiceTestCase):
    def test_a_freshly_imported_application_is_healthy(self) -> None:
        self.assertIs(self.service.health(self.import_appimage()), Health.OK)

    def test_a_deleted_appimage_is_detected(self) -> None:
        app = self.import_appimage()
        app.appimage.unlink()
        self.assertIs(self.service.health(app), Health.MISSING_APPIMAGE)

    def test_a_lost_execute_bit_is_detected(self) -> None:
        app = self.import_appimage()
        app.appimage.chmod(0o644)
        self.assertIs(self.service.health(app), Health.NOT_EXECUTABLE)

    def test_a_deleted_launcher_is_detected(self) -> None:
        app = self.import_appimage()
        app.desktop_entry.unlink()
        self.assertIs(self.service.health(app), Health.MISSING_LAUNCHER)

    def test_rebuilding_repairs_the_launcher_and_the_execute_bit(self) -> None:
        app = self.import_appimage()
        app.desktop_entry.unlink()
        app.appimage.chmod(0o644)

        repaired = self.service.rebuild_launcher(app)
        self.assertIs(self.service.health(repaired), Health.OK)
        self.assertTrue(os.access(repaired.appimage_path, os.X_OK))

    def test_rebuilding_a_missing_appimage_is_refused(self) -> None:
        from appimgify.utils.errors import StorageError

        app = self.import_appimage()
        app.appimage.unlink()
        with self.assertRaises(StorageError):
            self.service.rebuild_launcher(app)

    def test_problems_lists_only_broken_applications(self) -> None:
        healthy = self.import_appimage("Fine.AppImage")
        broken = self.import_appimage("Broken.AppImage")
        broken.appimage.unlink()

        problems = self.service.problems()
        self.assertEqual([app.id for app, _health in problems], [broken.id])
        self.assertNotIn(healthy.id, [app.id for app, _health in problems])


class FilteringTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.game = self.import_appimage("Zed.AppImage", name="Zed Game", categories=["Game"])
        self.tool = self.import_appimage(
            "Alpha.AppImage", name="Alpha Tool", categories=["Utility"]
        )

    def test_default_sort_is_alphabetical(self) -> None:
        self.assertEqual(
            [app.name for app in self.service.filtered()], ["Alpha Tool", "Zed Game"]
        )

    def test_recent_sort_puts_the_newest_first(self) -> None:
        self.assertEqual(
            [app.name for app in self.service.filtered(sort_order="recent")][0],
            "Alpha Tool",
        )

    def test_search_narrows_the_list(self) -> None:
        self.assertEqual([app.name for app in self.service.filtered("zed")], ["Zed Game"])

    def test_category_filtering(self) -> None:
        self.assertEqual(
            [app.name for app in self.service.filtered(category="Game")], ["Zed Game"]
        )

    def test_used_categories_reflects_the_library(self) -> None:
        self.assertEqual(self.service.used_categories(), ["Game", "Utility"])

    def test_search_and_category_combine(self) -> None:
        self.assertEqual(self.service.filtered("alpha", category="Game"), [])


class RemovalTests(ServiceTestCase):
    def test_removing_everything_clears_the_store_and_the_menu(self) -> None:
        app = self.import_appimage()
        storage = app.storage_dir
        launcher = app.desktop_entry

        self.service.remove(app, RemovalOptions(True, True))
        self.assertFalse(storage.exists())
        self.assertFalse(launcher.exists())
        self.assertEqual(self.service.apps, [])

    def test_removing_only_the_launcher_keeps_the_application(self) -> None:
        app = self.import_appimage()
        self.service.remove(app, RemovalOptions(remove_appimage=False, remove_launcher=True))

        self.assertFalse(app.desktop_entry.exists())
        self.assertTrue(app.appimage_exists())
        remaining = self.service.get(app.id)
        self.assertIsNotNone(remaining)
        assert remaining is not None
        self.assertEqual(remaining.desktop_entry_path, "")
        self.assertIs(self.service.health(remaining), Health.MISSING_LAUNCHER)

    def test_removing_only_the_appimage_drops_the_record(self) -> None:
        app = self.import_appimage()
        self.service.remove(app, RemovalOptions(remove_appimage=True, remove_launcher=False))
        self.assertEqual(self.service.apps, [])
        self.assertFalse(app.appimage_exists())

    def test_the_original_download_is_never_deleted(self) -> None:
        source = self.make_appimage("Keeper.AppImage")
        draft = self.service.prepare_import(source)
        app = self.service.commit_import(draft, draft.app)

        self.service.remove(app, RemovalOptions(True, True))
        self.assertTrue(source.is_file())

    def test_orphaned_launchers_can_be_cleaned_up(self) -> None:
        app = self.import_appimage()
        self.service.remove(app, RemovalOptions(remove_appimage=True, remove_launcher=False))

        self.assertEqual(len(self.service.orphaned_launchers()), 1)
        self.assertEqual(self.service.forget_orphans(), 1)
        self.assertEqual(self.service.orphaned_launchers(), [])


class EditingTests(ServiceTestCase):
    def test_saving_changes_regenerates_the_launcher(self) -> None:
        app = self.import_appimage()
        updated = self.service.apply_changes(
            app.copy_with(name="Renamed", description="New description")
        )
        text = updated.desktop_entry.read_text(encoding="utf-8")
        self.assertIn("Name=Renamed", text)
        self.assertIn("Comment=New description", text)
        self.assertFalse(app.desktop_entry.exists())

    def test_setting_an_icon_stores_it_beside_the_appimage(self) -> None:
        app = self.import_appimage()
        icon = self.root / "chosen.png"
        icon.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)

        updated = self.service.apply_changes(app, icon_source=icon)
        self.assertTrue(updated.icon_exists())
        self.assertEqual(updated.icon.parent, updated.storage_dir)
        self.assertIn(f"Icon={updated.icon_path}", updated.desktop_entry.read_text())

    def test_clearing_an_icon_removes_the_file_and_the_key(self) -> None:
        app = self.import_appimage()
        icon = self.root / "chosen.png"
        icon.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
        with_icon = self.service.apply_changes(app, icon_source=icon)
        stored = with_icon.icon

        cleared = self.service.clear_icon(with_icon)
        self.assertEqual(cleared.icon_path, "")
        assert stored is not None
        self.assertFalse(stored.exists())
        self.assertNotIn("Icon=", cleared.desktop_entry.read_text())

    def test_a_non_image_icon_is_rejected(self) -> None:
        from appimgify.utils.errors import StorageError

        app = self.import_appimage()
        junk = self.root / "notes.txt"
        junk.write_text("definitely not an image")
        with self.assertRaises(StorageError):
            self.service.apply_changes(app, icon_source=junk)


if __name__ == "__main__":
    unittest.main()
