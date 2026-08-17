"""Tests for the desktop-entry generator.

The generator is the part of Appimgify most likely to produce a subtly broken
file, so the awkward inputs — spaces, quotes, backslashes, ampersands, percent
signs and semicolons — are all covered here.
"""

from __future__ import annotations

import unittest

from helpers import SOURCE_ROOT  # noqa: F401  (puts src/ on sys.path)

from appimgify.desktop import entry
from appimgify.metadata import desktop_parser
from appimgify.models.managed_app import ManagedApp


def parse_entry(text: str) -> dict[str, str]:
    """Parse rendered entry text back into raw key/value pairs."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("["):
            key, _separator, value = line.partition("=")
            values[key] = value
    return values


def make_app(**overrides) -> ManagedApp:
    fields = {
        "name": "Example App",
        "appimage_path": "/home/tester/.local/share/appimages/Example/Example.AppImage",
    }
    fields.update(overrides)
    return ManagedApp(**fields)


class RenderingTests(unittest.TestCase):
    def test_minimal_entry_has_required_keys(self) -> None:
        values = parse_entry(entry.render(make_app()))
        self.assertEqual(values["Type"], "Application")
        self.assertEqual(values["Name"], "Example App")
        self.assertEqual(
            values["Exec"],
            "/home/tester/.local/share/appimages/Example/Example.AppImage",
        )
        self.assertEqual(values["Terminal"], "false")
        self.assertNotIn("Icon", values)

    def test_entry_starts_with_the_group_header(self) -> None:
        text = entry.render(make_app())
        self.assertTrue(text.startswith("[Desktop Entry]\n"))
        self.assertTrue(text.endswith("\n"))

    def test_optional_fields_are_omitted_when_empty(self) -> None:
        values = parse_entry(entry.render(make_app()))
        for key in ("GenericName", "Comment", "Categories", "Keywords", "Path"):
            self.assertNotIn(key, values)

    def test_categories_are_semicolon_terminated(self) -> None:
        values = parse_entry(entry.render(make_app(categories=["Game", "Utility"])))
        self.assertEqual(values["Categories"], "Game;Utility;")

    def test_terminal_and_startup_notify_round_trip(self) -> None:
        values = parse_entry(
            entry.render(make_app(terminal=True, startup_notify=False))
        )
        self.assertEqual(values["Terminal"], "true")
        self.assertEqual(values["StartupNotify"], "false")

    def test_tracking_key_records_the_application_id(self) -> None:
        app = make_app()
        values = parse_entry(entry.render(app))
        self.assertEqual(values[entry.TRACKING_KEY], app.id)

    def test_missing_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            entry.render(make_app(name="   "))

    def test_missing_executable_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            entry.render(make_app(appimage_path=""))


class EscapingTests(unittest.TestCase):
    """Paths containing spaces and other special characters."""

    def test_path_with_spaces_is_quoted(self) -> None:
        app = make_app(appimage_path="/home/a user/My Apps/Cool App.AppImage")
        values = parse_entry(entry.render(app))
        self.assertEqual(values["Exec"], '"/home/a user/My Apps/Cool App.AppImage"')

    def test_path_with_double_quotes_is_escaped_twice(self) -> None:
        app = make_app(appimage_path='/apps/He said "hi".AppImage')
        exec_value = parse_entry(entry.render(app))["Exec"]
        # Value-level unescaping happens first, then quote removal.
        unescaped = desktop_parser.unescape_value(exec_value)
        self.assertEqual(unescaped, '"/apps/He said \\"hi\\".AppImage"')

    def test_literal_backslash_becomes_four_backslashes(self) -> None:
        app = make_app(appimage_path="/apps/back\\slash.AppImage")
        exec_value = parse_entry(entry.render(app))["Exec"]
        self.assertIn("\\\\\\\\", exec_value)

    def test_dollar_and_backtick_are_neutralised(self) -> None:
        app = make_app(appimage_path="/apps/$HOME `whoami`.AppImage")
        exec_value = parse_entry(entry.render(app))["Exec"]
        unescaped = desktop_parser.unescape_value(exec_value)
        self.assertEqual(unescaped, '"/apps/\\$HOME \\`whoami\\`.AppImage"')

    def test_percent_is_doubled_so_it_is_not_a_field_code(self) -> None:
        app = make_app(arguments=["100%"])
        exec_value = parse_entry(entry.render(app))["Exec"]
        self.assertTrue(exec_value.endswith("100%%"))

    def test_newline_in_a_name_cannot_break_the_file(self) -> None:
        values = parse_entry(entry.render(make_app(name="Bad\nName=evil")))
        self.assertEqual(values["Name"], "Bad\\nName=evil")
        self.assertNotIn("evil", values)

    def test_semicolons_inside_a_category_are_escaped(self) -> None:
        app = make_app()
        app.keywords = ["one;two", "three"]
        values = parse_entry(entry.render(app))
        self.assertEqual(values["Keywords"], "one\\\\;two;three;")

    def test_arguments_are_quoted_individually(self) -> None:
        app = make_app(
            appimage_path="/apps/Simple.AppImage",
            arguments=["--profile", "my profile", "--flag"],
        )
        values = parse_entry(entry.render(app))
        self.assertEqual(
            values["Exec"], '/apps/Simple.AppImage --profile "my profile" --flag'
        )

    def test_ampersand_in_a_name_is_kept_verbatim(self) -> None:
        values = parse_entry(entry.render(make_app(name="Rock & Roll")))
        self.assertEqual(values["Name"], "Rock & Roll")

    def test_working_directory_with_spaces(self) -> None:
        app = make_app(working_directory="/home/a user/Documents/My Games")
        values = parse_entry(entry.render(app))
        self.assertEqual(values["Path"], "/home/a user/Documents/My Games")

    def test_icon_path_with_spaces_is_not_quoted(self) -> None:
        # Icon is a plain string value, not a command line.
        app = make_app(icon_path="/home/a user/icons/my icon.png")
        values = parse_entry(entry.render(app))
        self.assertEqual(values["Icon"], "/home/a user/icons/my icon.png")


class QuotingUnitTests(unittest.TestCase):
    def test_plain_argument_is_untouched(self) -> None:
        self.assertEqual(entry.quote_exec_argument("--verbose"), "--verbose")

    def test_empty_argument_is_preserved_as_empty_quotes(self) -> None:
        self.assertEqual(entry.quote_exec_argument(""), '""')

    def test_reserved_characters_force_quoting(self) -> None:
        for char in (" ", ">", "<", "|", "&", ";", "*", "?", "#", "(", ")", "~"):
            with self.subTest(char=char):
                self.assertTrue(entry.quote_exec_argument(f"a{char}b").startswith('"'))

    def test_build_exec_joins_program_and_arguments(self) -> None:
        self.assertEqual(
            entry.build_exec("/bin/app", ["-x", "two words"]),
            '/bin/app -x "two words"',
        )


class FileNameTests(unittest.TestCase):
    def test_generated_name_is_namespaced_and_safe(self) -> None:
        name = entry.desktop_file_name(make_app(name="My Cool App!"))
        self.assertEqual(name, "appimgify-my-cool-app.desktop")

    def test_non_ascii_names_produce_a_usable_file_name(self) -> None:
        name = entry.desktop_file_name(make_app(name="Übergrübler"))
        self.assertTrue(name.endswith(".desktop"))
        self.assertTrue(name.isascii())
        self.assertNotIn("/", name)

    def test_name_of_only_symbols_falls_back_to_the_id(self) -> None:
        app = make_app(name="???")
        name = entry.desktop_file_name(app)
        self.assertTrue(name.startswith("appimgify-"))
        self.assertNotIn("?", name)

    def test_explicit_launcher_name_is_honoured(self) -> None:
        app = make_app(desktop_file_name="my-launcher.desktop")
        self.assertEqual(entry.desktop_file_name(app), "my-launcher.desktop")

    def test_explicit_launcher_name_cannot_escape_the_directory(self) -> None:
        app = make_app(desktop_file_name="../../evil")
        name = entry.desktop_file_name(app)
        self.assertNotIn("/", name)
        self.assertTrue(name.endswith(".desktop"))


if __name__ == "__main__":
    unittest.main()
