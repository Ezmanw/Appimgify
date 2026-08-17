"""Tests for AppImage detection and validation."""

from __future__ import annotations

import os
import unittest

from helpers import EXPECTED_PAYLOAD_OFFSET, TempDirTestCase, write_fake_appimage

from appimgify.appimages import validator
from appimgify.utils.errors import ValidationError


class ValidationTests(TempDirTestCase):
    def test_type_2_appimage_is_recognised(self) -> None:
        path = self.make_appimage()
        info = validator.inspect(path)
        self.assertEqual(info.appimage_type, validator.TYPE_SQUASHFS)
        self.assertTrue(info.has_magic)
        self.assertTrue(info.supports_extraction)
        self.assertEqual(info.warnings, [])
        self.assertEqual(info.type_label, "AppImage (type 2)")

    def test_type_1_appimage_is_recognised_but_flagged(self) -> None:
        path = self.make_appimage(name="Old.AppImage", appimage_type=1)
        info = validator.inspect(path)
        self.assertEqual(info.appimage_type, validator.TYPE_ISO)
        self.assertFalse(info.supports_extraction)
        self.assertTrue(info.warnings)

    def test_payload_offset_is_read_from_the_elf_header(self) -> None:
        info = validator.inspect(self.make_appimage())
        self.assertEqual(info.payload_offset, EXPECTED_PAYLOAD_OFFSET)

    def test_elf_without_magic_is_accepted_with_a_warning(self) -> None:
        path = self.make_appimage(name="Unsigned.AppImage", appimage_type=None)
        info = validator.inspect(path)
        self.assertFalse(info.has_magic)
        self.assertTrue(any("signature" in warning for warning in info.warnings))

    def test_unknown_format_revision_is_reported(self) -> None:
        path = self.make_appimage(name="Future.AppImage", appimage_type=9)
        info = validator.inspect(path)
        self.assertTrue(any("format 9" in warning for warning in info.warnings))

    def test_plain_text_file_is_rejected(self) -> None:
        path = self.root / "notes.txt"
        path.write_text("x" * 20000)
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(path)
        self.assertEqual(caught.exception.title, "Not an AppImage")

    def test_tiny_file_is_rejected(self) -> None:
        path = self.root / "stub.AppImage"
        write_fake_appimage(path, size=128)
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(path)
        self.assertEqual(caught.exception.title, "File is too small")

    def test_missing_file_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(self.root / "nope.AppImage")
        self.assertEqual(caught.exception.title, "File not found")

    def test_directory_is_rejected(self) -> None:
        directory = self.root / "folder"
        directory.mkdir()
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(directory)
        self.assertEqual(caught.exception.title, "That is a folder")

    def test_unreadable_file_is_reported_clearly(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can read anything")
        path = self.make_appimage(name="Locked.AppImage")
        path.chmod(0o000)
        self.addCleanup(path.chmod, 0o644)
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(path)
        self.assertEqual(caught.exception.title, "File cannot be read")

    def test_errors_carry_user_facing_text(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validator.inspect(self.root / "missing.AppImage")
        self.assertTrue(caught.exception.title)
        self.assertTrue(caught.exception.detail)

    def test_looks_like_appimage_never_raises(self) -> None:
        self.assertTrue(validator.looks_like_appimage(self.make_appimage()))
        self.assertFalse(validator.looks_like_appimage(self.root / "absent"))


class FallbackNameTests(unittest.TestCase):
    def test_version_and_architecture_are_stripped(self) -> None:
        from pathlib import Path

        from appimgify.metadata.extractor import fallback_name

        self.assertEqual(
            fallback_name(Path("/tmp/Krita-5.2.2-x86_64.AppImage")), "Krita"
        )
        self.assertEqual(
            fallback_name(Path("/tmp/Some_Cool_App-v1.0.AppImage")), "Some Cool App"
        )

    def test_a_name_is_always_produced(self) -> None:
        from pathlib import Path

        from appimgify.metadata.extractor import fallback_name

        self.assertTrue(fallback_name(Path("/tmp/1.2.3.AppImage")))


if __name__ == "__main__":
    unittest.main()
