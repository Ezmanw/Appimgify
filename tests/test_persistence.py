"""Tests for the library, settings and preset files.

Corruption handling matters as much as the happy path here: a damaged file
must never stop the application from starting.
"""

from __future__ import annotations

import json
import unittest

from helpers import TempDirTestCase

from appimgify.models.managed_app import ManagedApp
from appimgify.models.preset import Preset
from appimgify.persistence.config import Settings, SettingsStore
from appimgify.persistence.library import Library
from appimgify.persistence.presets_store import PresetStore
from appimgify.utils.paths import config_dir, data_dir, default_appimage_dir


def make_app(name: str = "Example") -> ManagedApp:
    return ManagedApp(name=name, appimage_path=f"/tmp/{name}.AppImage")


class LibraryTests(TempDirTestCase):
    def test_saved_applications_are_read_back(self) -> None:
        library = Library()
        library.load()
        app = library.add(make_app())

        reopened = Library()
        reopened.load()
        self.assertEqual(len(reopened), 1)
        restored = reopened.get(app.id)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.name, "Example")

    def test_library_lives_in_the_xdg_data_directory(self) -> None:
        library = Library()
        library.load()
        library.add(make_app())
        self.assertEqual(library.path, data_dir() / "library.json")
        self.assertTrue(library.path.is_file())

    def test_the_file_is_human_readable_json(self) -> None:
        library = Library()
        library.load()
        library.add(make_app())
        payload = json.loads(library.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["applications"][0]["name"], "Example")

    def test_missing_file_loads_as_an_empty_library(self) -> None:
        library = Library()
        self.assertEqual(library.load(), [])
        self.assertFalse(library.recovered_from_corruption)

    def test_corrupted_file_is_quarantined_not_lost(self) -> None:
        path = data_dir() / "library.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{this is not json", encoding="utf-8")

        library = Library()
        self.assertEqual(library.load(), [])
        self.assertTrue(library.recovered_from_corruption)
        self.assertTrue(path.with_suffix(".json.corrupt").is_file())

    def test_damaged_records_are_skipped_and_the_rest_survive(self) -> None:
        path = data_dir() / "library.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "applications": [
                        {"name": "Good", "appimage_path": "/tmp/Good.AppImage"},
                        {"appimage_path": "/tmp/Nameless.AppImage"},
                        "not even an object",
                    ],
                }
            ),
            encoding="utf-8",
        )
        library = Library()
        apps = library.load()
        self.assertEqual([app.name for app in apps], ["Good"])
        self.assertEqual(library.skipped_records, 2)

    def test_a_bare_list_of_applications_is_accepted(self) -> None:
        path = data_dir() / "library.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([{"name": "Legacy", "appimage_path": "/tmp/L.AppImage"}]),
            encoding="utf-8",
        )
        self.assertEqual([app.name for app in Library().load()], ["Legacy"])

    def test_repeated_ids_are_collapsed(self) -> None:
        record = make_app().to_dict()
        path = data_dir() / "library.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"applications": [record, dict(record)]}), encoding="utf-8"
        )
        library = Library()
        self.assertEqual(len(library.load()), 1)
        self.assertEqual(library.skipped_records, 1)

    def test_update_replaces_the_matching_record(self) -> None:
        library = Library()
        library.load()
        app = library.add(make_app())
        library.update(app.copy_with(name="Renamed"))
        self.assertEqual(len(library), 1)
        restored = library.get(app.id)
        assert restored is not None
        self.assertEqual(restored.name, "Renamed")

    def test_remove_returns_the_removed_record(self) -> None:
        library = Library()
        library.load()
        app = library.add(make_app())
        self.assertIsNotNone(library.remove(app.id))
        self.assertIsNone(library.remove(app.id))
        self.assertEqual(len(library), 0)


class SettingsTests(TempDirTestCase):
    def test_defaults_point_at_the_documented_locations(self) -> None:
        settings = SettingsStore().load()
        self.assertEqual(settings.appimage_path, default_appimage_dir())
        self.assertTrue(str(settings.appimage_path).endswith("/.local/share/appimages"))
        self.assertTrue(str(settings.launcher_path).endswith("/.local/share/applications"))

    def test_settings_round_trip(self) -> None:
        store = SettingsStore()
        settings = store.load()
        settings.color_scheme = "dark"
        settings.appimage_dir = str(self.root / "elsewhere")
        settings.create_launcher_on_import = False
        store.save(settings)

        restored = SettingsStore().load()
        self.assertEqual(restored.color_scheme, "dark")
        self.assertEqual(restored.appimage_path, self.root / "elsewhere")
        self.assertFalse(restored.create_launcher_on_import)

    def test_settings_live_in_the_xdg_config_directory(self) -> None:
        store = SettingsStore()
        store.load()
        store.save()
        self.assertEqual(store.path, config_dir() / "settings.json")
        self.assertTrue(store.path.is_file())

    def test_corrupted_settings_fall_back_to_defaults(self) -> None:
        path = config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<<<not json>>>", encoding="utf-8")

        store = SettingsStore()
        settings = store.load()
        self.assertTrue(store.recovered_from_corruption)
        self.assertEqual(settings.color_scheme, "system")
        self.assertTrue(path.with_suffix(".json.corrupt").is_file())

    def test_invalid_values_are_replaced_individually(self) -> None:
        path = config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "color_scheme": "neon",
                    "duplicate_action": "explode",
                    "create_launcher_on_import": "yes",
                    "window_width": -5,
                    "appimage_dir": str(self.root / "kept"),
                }
            ),
            encoding="utf-8",
        )
        settings = SettingsStore().load()
        self.assertEqual(settings.color_scheme, "system")
        self.assertEqual(settings.duplicate_action, "ask")
        self.assertTrue(settings.create_launcher_on_import)
        self.assertGreaterEqual(settings.window_width, 360)
        self.assertEqual(settings.appimage_path, self.root / "kept")

    def test_tilde_paths_are_expanded(self) -> None:
        settings = Settings(appimage_dir="~/Applications")
        self.assertEqual(settings.appimage_path, self.home / "Applications")


class PresetStoreTests(TempDirTestCase):
    def test_builtin_presets_are_always_present(self) -> None:
        store = PresetStore()
        names = [preset.name for preset in store.load()]
        self.assertIn("Gaming App", names)
        self.assertIn("Utility", names)

    def test_user_presets_are_saved_and_reloaded(self) -> None:
        store = PresetStore()
        store.load()
        store.add(Preset(name="My Setup", categories=["Graphics"], terminal=True))

        reopened = PresetStore()
        reopened.load()
        saved = [preset for preset in reopened.user_presets() if preset.name == "My Setup"]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].categories, ["Graphics"])

    def test_builtin_presets_are_not_written_to_disk(self) -> None:
        store = PresetStore()
        store.load()
        store.save()
        payload = json.loads(store.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["presets"], [])

    def test_saving_the_same_name_twice_replaces_it(self) -> None:
        store = PresetStore()
        store.load()
        store.add(Preset(name="Same", categories=["Game"]))
        store.add(Preset(name="Same", categories=["Office"]))
        self.assertEqual(len(store.user_presets()), 1)
        self.assertEqual(store.user_presets()[0].categories, ["Office"])

    def test_removing_a_user_preset(self) -> None:
        store = PresetStore()
        store.load()
        preset = store.add(Preset(name="Temporary"))
        self.assertTrue(store.remove(preset.id))
        self.assertFalse(store.remove(preset.id))

    def test_corrupted_presets_fall_back_to_the_builtins(self) -> None:
        path = config_dir() / "presets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("nope", encoding="utf-8")
        store = PresetStore()
        presets = store.load()
        self.assertTrue(store.recovered_from_corruption)
        self.assertEqual(store.user_presets(), [])
        self.assertTrue(presets)


class AtomicWriteTests(TempDirTestCase):
    def test_no_temporary_files_are_left_behind(self) -> None:
        library = Library()
        library.load()
        library.add(make_app())
        leftovers = [
            path.name for path in library.path.parent.iterdir() if path.name.startswith(".")
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
