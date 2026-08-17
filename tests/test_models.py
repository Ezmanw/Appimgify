"""Tests for the data model and its serialisation."""

from __future__ import annotations

import unittest

from helpers import SOURCE_ROOT  # noqa: F401  (puts src/ on sys.path)

from appimgify.models import categories as categories_module
from appimgify.models.managed_app import ManagedApp
from appimgify.models.preset import Preset, builtin_presets


def sample_app() -> ManagedApp:
    return ManagedApp(
        name="Example App",
        appimage_path="/home/tester/.local/share/appimages/Example/Example.AppImage",
        generic_name="Text Editor",
        description="Edits text",
        version="1.2.3",
        icon_path="/home/tester/.local/share/appimages/Example/icon.png",
        categories=["Development", "Utility"],
        arguments=["--safe-mode", "two words"],
        working_directory="/home/tester",
        terminal=True,
        startup_notify=False,
        keywords=["editor", "code"],
        mime_types=["text/plain"],
        desktop_entry_path="/home/tester/.local/share/applications/x.desktop",
    )


class SerialisationTests(unittest.TestCase):
    def test_round_trip_preserves_every_field(self) -> None:
        original = sample_app()
        restored = ManagedApp.from_dict(original.to_dict())
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_ids_are_unique_per_application(self) -> None:
        self.assertNotEqual(sample_app().id, sample_app().id)

    def test_missing_optional_fields_get_defaults(self) -> None:
        restored = ManagedApp.from_dict({"name": "X", "appimage_path": "/tmp/X.AppImage"})
        assert restored is not None
        self.assertEqual(restored.categories, [])
        self.assertFalse(restored.terminal)
        self.assertTrue(restored.startup_notify)
        self.assertTrue(restored.id)

    def test_records_without_a_name_are_rejected(self) -> None:
        self.assertIsNone(ManagedApp.from_dict({"appimage_path": "/tmp/x"}))

    def test_records_without_a_path_are_rejected(self) -> None:
        self.assertIsNone(ManagedApp.from_dict({"name": "X"}))

    def test_non_dict_payloads_are_rejected(self) -> None:
        for payload in (None, [], "text", 42):
            self.assertIsNone(ManagedApp.from_dict(payload))

    def test_wrongly_typed_fields_fall_back_to_defaults(self) -> None:
        restored = ManagedApp.from_dict(
            {
                "name": "X",
                "appimage_path": "/tmp/X.AppImage",
                "categories": "Game",  # should be a list
                "terminal": "yes",  # should be a bool
                "arguments": [1, 2, "--real"],
                "imported_at": "recently",
            }
        )
        assert restored is not None
        self.assertEqual(restored.categories, [])
        self.assertFalse(restored.terminal)
        self.assertEqual(restored.arguments, ["--real"])
        self.assertIsInstance(restored.imported_at, float)

    def test_unknown_categories_are_dropped_on_load(self) -> None:
        restored = ManagedApp.from_dict(
            {
                "name": "X",
                "appimage_path": "/tmp/X.AppImage",
                "categories": ["Game", "NotARealCategory"],
            }
        )
        assert restored is not None
        self.assertEqual(restored.categories, ["Game"])


class BehaviourTests(unittest.TestCase):
    def test_copy_with_refreshes_the_timestamp(self) -> None:
        app = sample_app()
        updated = app.copy_with(name="Renamed")
        self.assertEqual(updated.name, "Renamed")
        self.assertEqual(updated.id, app.id)
        self.assertGreaterEqual(updated.updated_at, app.updated_at)

    def test_arguments_text_is_shell_quoted(self) -> None:
        self.assertEqual(sample_app().arguments_text, "--safe-mode 'two words'")

    def test_search_matches_name_description_and_file_name(self) -> None:
        app = sample_app()
        self.assertTrue(app.matches("example"))
        self.assertTrue(app.matches("EDITS"))
        self.assertTrue(app.matches("Example.AppImage"))
        self.assertTrue(app.matches("development"))
        self.assertFalse(app.matches("gimp"))

    def test_empty_search_matches_everything(self) -> None:
        self.assertTrue(sample_app().matches("   "))

    def test_subtitle_falls_back_to_the_file_name(self) -> None:
        bare = ManagedApp(name="X", appimage_path="/tmp/Thing.AppImage")
        self.assertEqual(bare.display_subtitle(), "Thing.AppImage")


class CategoryTests(unittest.TestCase):
    def test_normalise_keeps_menu_order_and_drops_duplicates(self) -> None:
        self.assertEqual(
            categories_module.normalise(["Utility", "Game", "Game", "Nonsense"]),
            ["Game", "Utility"],
        )

    def test_labels_fall_back_to_the_raw_value(self) -> None:
        self.assertEqual(categories_module.label_for("Network"), "Internet")
        self.assertEqual(categories_module.label_for("Custom"), "Custom")

    def test_describe_handles_the_empty_case(self) -> None:
        self.assertEqual(categories_module.describe([]), "No categories")


class PresetTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        preset = Preset(
            name="Gaming",
            categories=["Game"],
            arguments=["--fullscreen"],
            terminal=False,
        )
        restored = Preset.from_dict(preset.to_dict())
        assert restored is not None
        self.assertEqual(restored.to_dict(), preset.to_dict())

    def test_applying_a_preset_leaves_identity_alone(self) -> None:
        app = sample_app()
        preset = Preset(name="Gaming", categories=["Game"], terminal=False)
        result = preset.apply_to(app)
        self.assertEqual(result.categories, ["Game"])
        self.assertFalse(result.terminal)
        self.assertEqual(result.name, app.name)
        self.assertEqual(result.appimage_path, app.appimage_path)

    def test_capturing_a_preset_excludes_the_appimage(self) -> None:
        preset = Preset.from_app("Captured", sample_app())
        self.assertNotIn("appimage_path", preset.to_dict())
        self.assertEqual(preset.categories, ["Development", "Utility"])

    def test_builtin_presets_are_valid(self) -> None:
        for preset in builtin_presets():
            with self.subTest(preset=preset.name):
                self.assertTrue(preset.builtin)
                self.assertEqual(
                    categories_module.normalise(preset.categories), preset.categories
                )

    def test_unnamed_presets_are_rejected(self) -> None:
        self.assertIsNone(Preset.from_dict({"categories": ["Game"]}))
        self.assertIsNone(Preset.from_dict("nonsense"))


if __name__ == "__main__":
    unittest.main()
