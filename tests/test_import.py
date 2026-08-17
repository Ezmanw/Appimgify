"""Tests for the store, the import pipeline and launcher installation."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest

from helpers import TempDirTestCase

from appimgify.appimages.importer import AppImageImporter, find_duplicate
from appimgify.appimages.storage import AppImageStore
from appimgify.desktop import entry as entry_module
from appimgify.desktop.installer import DesktopEntryInstaller
from appimgify.models.managed_app import ManagedApp
from appimgify.utils.errors import ImportError_, StorageError, ValidationError


class ImportTestCase(TempDirTestCase):
    """Wires a store, an installer and an importer against temp directories."""

    def setUp(self) -> None:
        super().setUp()
        self.store_root = self.data_home / "appimages"
        self.launcher_root = self.data_home / "applications"
        self.store = AppImageStore(self.store_root)
        self.installer = DesktopEntryInstaller(self.launcher_root)
        self.importer = AppImageImporter(self.store, self.installer)

    def import_file(self, path, existing=None, **overrides) -> ManagedApp:
        draft = self.importer.prepare(path, existing or [])
        app = draft.app.copy_with(**overrides) if overrides else draft.app
        return self.importer.commit(draft, app)


class StorageTests(ImportTestCase):
    def test_the_store_is_created_on_demand(self) -> None:
        self.assertFalse(self.store_root.exists())
        self.store.ensure_ready()
        self.assertTrue(self.store_root.is_dir())

    def test_an_unwritable_location_is_reported(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can write anywhere")
        locked = self.root / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        with self.assertRaises(StorageError):
            AppImageStore(locked / "store").ensure_ready()

    def test_allocated_directories_never_collide(self) -> None:
        first = self.store.allocate_directory("Example")
        second = self.store.allocate_directory("Example")
        self.assertNotEqual(first, second)
        self.assertEqual(first.name, "Example")
        self.assertEqual(second.name, "Example-2")

    def test_removal_refuses_paths_outside_the_store(self) -> None:
        outside = self.root / "precious"
        outside.mkdir()
        with self.assertRaises(StorageError):
            self.store.remove_application(outside)
        self.assertTrue(outside.is_dir())


class ImportPipelineTests(ImportTestCase):
    def test_a_full_import_produces_a_working_application(self) -> None:
        source = self.make_appimage("Krita-5.2.2-x86_64.AppImage")
        app = self.import_file(source)

        self.assertTrue(app.appimage_exists())
        self.assertTrue(app.launcher_exists())
        self.assertTrue(self.store.owns(app.appimage))
        self.assertEqual(app.appimage_filename, "Krita-5.2.2-x86_64.AppImage")
        self.assertEqual(app.name, "Krita")

    def test_the_stored_appimage_is_executable(self) -> None:
        app = self.import_file(self.make_appimage())
        self.assertTrue(os.access(app.appimage_path, os.X_OK))

    def test_the_original_file_is_left_untouched(self) -> None:
        source = self.make_appimage()
        original = source.read_bytes()
        self.import_file(source)
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(os.access(source, os.X_OK))

    def test_the_launcher_points_at_the_managed_copy(self) -> None:
        app = self.import_file(self.make_appimage())
        text = app.desktop_entry.read_text(encoding="utf-8")
        self.assertIn(f"Exec={app.appimage_path}", text)
        self.assertIn("X-Appimgify-Managed=true", text)
        self.assertNotIn("/home/user", text)

    def test_the_launcher_lands_in_the_user_application_directory(self) -> None:
        app = self.import_file(self.make_appimage())
        self.assertEqual(app.desktop_entry.parent, self.launcher_root)
        self.assertTrue(app.desktop_entry.name.endswith(".desktop"))

    def test_names_with_spaces_survive_the_whole_pipeline(self) -> None:
        source = self.make_appimage("My Cool App.AppImage")
        app = self.import_file(source, name="My Cool App")
        self.assertTrue(app.appimage_exists())
        text = app.desktop_entry.read_text(encoding="utf-8")
        self.assertIn('Exec="', text)  # the path contains a space, so it is quoted
        self.assertIn("Name=My Cool App", text)

    def test_importing_can_skip_launcher_creation(self) -> None:
        draft = self.importer.prepare(self.make_appimage(), [])
        app = self.importer.commit(draft, draft.app, create_launcher=False)
        self.assertTrue(app.appimage_exists())
        self.assertEqual(app.desktop_entry_path, "")

    def test_importing_a_non_appimage_is_rejected_before_anything_is_written(self) -> None:
        junk = self.root / "notes.txt"
        junk.write_text("x" * 20000)
        with self.assertRaises(ValidationError):
            self.importer.prepare(junk, [])
        self.assertFalse(self.store_root.exists())

    def test_a_missing_source_at_commit_time_is_reported(self) -> None:
        source = self.make_appimage()
        draft = self.importer.prepare(source, [])
        self.addCleanup(draft.release)
        source.unlink()
        with self.assertRaises(ImportError_):
            self.importer.commit(draft, draft.app)

    def test_a_failed_import_leaves_no_debris(self) -> None:
        source = self.make_appimage()
        draft = self.importer.prepare(source, [])
        self.addCleanup(draft.release)
        source.unlink()
        with self.assertRaises(ImportError_):
            self.importer.commit(draft, draft.app)
        self.assertEqual(list(self.store_root.iterdir()), [])

    def test_a_file_already_in_the_store_cannot_be_imported_again(self) -> None:
        app = self.import_file(self.make_appimage())
        with self.assertRaises(ValidationError):
            self.importer.prepare(app.appimage, [])


class DuplicateTests(ImportTestCase):
    def test_two_imports_of_the_same_file_are_kept_apart(self) -> None:
        source = self.make_appimage("Example.AppImage")
        first = self.import_file(source)
        second = self.import_file(source)

        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.appimage_path, second.appimage_path)
        self.assertTrue(first.appimage_exists())
        self.assertTrue(second.appimage_exists())

    def test_an_existing_appimage_is_never_overwritten(self) -> None:
        source = self.make_appimage("Example.AppImage")
        first = self.import_file(source)
        marker = b"original contents"
        first.appimage.write_bytes(marker)

        self.import_file(source)
        self.assertEqual(first.appimage.read_bytes(), marker)

    def test_duplicate_detection_matches_by_name(self) -> None:
        existing = ManagedApp(name="Krita", appimage_path="/tmp/Krita.AppImage")
        found = find_duplicate("Krita", self.make_appimage("Krita-new.AppImage"), [existing])
        self.assertIs(found, existing)

    def test_duplicate_detection_matches_by_file_name(self) -> None:
        existing = ManagedApp(name="Something Else", appimage_path="/tmp/Krita.AppImage")
        found = find_duplicate("Anything", self.make_appimage("Krita.AppImage"), [existing])
        self.assertIs(found, existing)

    def test_unrelated_applications_are_not_flagged(self) -> None:
        existing = ManagedApp(name="Krita", appimage_path="/tmp/Krita.AppImage")
        self.assertIsNone(
            find_duplicate("Inkscape", self.make_appimage("Inkscape.AppImage"), [existing])
        )

    def test_the_importer_flags_duplicates_on_the_draft(self) -> None:
        source = self.make_appimage("Example.AppImage")
        first = self.import_file(source)
        draft = self.importer.prepare(source, [first])
        draft.release()
        self.assertIsNotNone(draft.duplicate_of)


class ReplacementTests(ImportTestCase):
    def test_replacing_keeps_the_launcher_configuration(self) -> None:
        app = self.import_file(self.make_appimage("Example.AppImage"))
        configured = app.copy_with(
            name="Configured", categories=["Game"], arguments=["--flag"]
        )

        replacement = self.root / "downloads" / "Example-2.0.AppImage"
        replacement.write_bytes(self.make_appimage("staging.AppImage").read_bytes())

        updated = self.importer.replace(configured, replacement)
        self.assertEqual(updated.id, app.id)
        self.assertEqual(updated.name, "Configured")
        self.assertEqual(updated.categories, ["Game"])
        self.assertEqual(updated.arguments, ["--flag"])
        self.assertEqual(updated.appimage.name, "Example-2.0.AppImage")
        self.assertTrue(os.access(updated.appimage_path, os.X_OK))

    def test_the_old_appimage_is_gone_after_a_successful_replacement(self) -> None:
        app = self.import_file(self.make_appimage("Example.AppImage"))
        old_path = app.appimage
        replacement = self.make_appimage("Example-2.0.AppImage")
        self.importer.replace(app, replacement)
        self.assertFalse(old_path.exists())

    def test_an_invalid_replacement_leaves_the_original_in_place(self) -> None:
        app = self.import_file(self.make_appimage("Example.AppImage"))
        contents = app.appimage.read_bytes()

        junk = self.root / "junk.txt"
        junk.write_text("y" * 20000)
        with self.assertRaises(ValidationError):
            self.importer.replace(app, junk)

        self.assertTrue(app.appimage_exists())
        self.assertEqual(app.appimage.read_bytes(), contents)

    def test_replacing_a_missing_appimage_is_refused(self) -> None:
        app = self.import_file(self.make_appimage("Example.AppImage"))
        app.appimage.unlink()
        with self.assertRaises(StorageError):
            self.importer.replace(app, self.make_appimage("Example-2.0.AppImage"))


class DesktopFileValidationTests(ImportTestCase):
    """Checks generated launchers against the freedesktop.org validator.

    Skipped when ``desktop-file-validate`` is not installed.
    """

    def setUp(self) -> None:
        super().setUp()
        self.validator = shutil.which("desktop-file-validate")
        if self.validator is None:
            self.skipTest("desktop-file-validate is not installed")

    def assert_valid(self, app: ManagedApp) -> None:
        result = subprocess.run(
            [self.validator, str(app.desktop_entry)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0, f"{result.stdout}{result.stderr}"
        )

    def test_a_plain_launcher_validates(self) -> None:
        self.assert_valid(self.import_file(self.make_appimage()))

    def test_a_launcher_for_an_awkward_path_validates(self) -> None:
        source = self.make_appimage("A weird 'name' & symbols!.AppImage")
        self.assert_valid(self.import_file(source, name="A weird 'name' & symbols!"))

    def test_a_fully_populated_launcher_validates(self) -> None:
        app = self.import_file(
            self.make_appimage("Full.AppImage"),
            name="Full Example",
            generic_name="Example Application",
            description="Does a bit of everything",
            categories=["Game", "Utility"],
            keywords=["one", "two"],
            arguments=["--profile", "my profile"],
            working_directory="/tmp",
            terminal=True,
            startup_notify=False,
            single_main_window=True,
        )
        self.assert_valid(app)


class InstallerTests(ImportTestCase):
    def test_renaming_an_application_removes_the_old_launcher(self) -> None:
        app = self.import_file(self.make_appimage())
        original_launcher = app.desktop_entry

        renamed = app.copy_with(name="Totally Different")
        new_launcher = self.installer.install(renamed)

        self.assertNotEqual(new_launcher, original_launcher)
        self.assertFalse(original_launcher.exists())
        self.assertTrue(new_launcher.is_file())

    def test_uninstall_only_deletes_our_own_launchers(self) -> None:
        app = self.import_file(self.make_appimage())
        foreign = self.launcher_root / entry_module.desktop_file_name(app)
        foreign.write_text("[Desktop Entry]\nType=Application\nName=Someone Else\n")

        self.assertFalse(self.installer.uninstall(app))
        self.assertTrue(foreign.is_file())

    def test_uninstall_removes_a_managed_launcher(self) -> None:
        app = self.import_file(self.make_appimage())
        self.assertTrue(self.installer.uninstall(app))
        self.assertFalse(app.desktop_entry.exists())

    def test_orphaned_launchers_are_detected(self) -> None:
        app = self.import_file(self.make_appimage())
        self.assertEqual(self.installer.find_orphans({app.id}), [])
        self.assertEqual(self.installer.find_orphans(set()), [app.desktop_entry])

    def test_launchers_are_written_with_the_expected_permissions(self) -> None:
        app = self.import_file(self.make_appimage())
        mode = app.desktop_entry.stat().st_mode & 0o777
        self.assertEqual(mode, 0o755)


if __name__ == "__main__":
    unittest.main()
