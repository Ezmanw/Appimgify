"""Shared test fixtures.

Builds byte-accurate fake AppImages so validation, offset computation and the
import pipeline can be exercised without shipping a real 100 MB bundle.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def elf_header(appimage_type: int | None = 2) -> bytearray:
    """A well-formed 64-bit little-endian ELF header.

    ``appimage_type`` writes the AppImage magic into the padding bytes, or
    leaves them zeroed when ``None`` (an ELF binary that is not an AppImage).
    """
    header = bytearray(64)
    header[0:4] = b"\x7fELF"
    header[4] = 2  # 64-bit
    header[5] = 1  # little endian
    header[6] = 1  # ELF version
    if appimage_type is not None:
        header[8:11] = bytes((0x41, 0x49, appimage_type))
    struct.pack_into("<H", header, 16, 2)  # e_type: executable
    struct.pack_into("<H", header, 18, 0x3E)  # e_machine: x86-64
    struct.pack_into("<I", header, 20, 1)  # e_version
    struct.pack_into("<Q", header, 40, 1024)  # e_shoff
    struct.pack_into("<H", header, 52, 64)  # e_ehsize
    struct.pack_into("<H", header, 58, 64)  # e_shentsize
    struct.pack_into("<H", header, 60, 4)  # e_shnum
    return header


#: Payload offset implied by :func:`elf_header` (e_shoff + e_shentsize * e_shnum).
EXPECTED_PAYLOAD_OFFSET = 1024 + 64 * 4


def write_fake_appimage(
    path: Path, *, appimage_type: int | None = 2, size: int = 32 * 1024
) -> Path:
    """Write a file that validates as an AppImage but contains no payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = elf_header(appimage_type)
    body.extend(b"\0" * max(0, size - len(body)))
    path.write_bytes(bytes(body))
    os.chmod(path, 0o644)
    return path


class TempDirTestCase(unittest.TestCase):
    """Base class giving each test an isolated XDG environment."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="appimgify-test-")
        self.root = Path(self._temp.name)
        self.home = self.root / "home"
        self.config_home = self.home / ".config"
        self.data_home = self.home / ".local" / "share"
        for directory in (self.config_home, self.data_home):
            directory.mkdir(parents=True, exist_ok=True)

        self._environment = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_DATA_HOME": str(self.data_home),
        }
        self._saved = {key: os.environ.get(key) for key in self._environment}
        os.environ.update(self._environment)
        self.addCleanup(self._restore_environment)
        self.addCleanup(self._temp.cleanup)

    def _restore_environment(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ------------------------------------------------------------------
    def make_appimage(self, name: str = "Example-1.2.3-x86_64.AppImage", **kwargs) -> Path:
        """Create a fake AppImage in a “downloads” directory."""
        downloads = self.root / "downloads"
        return write_fake_appimage(downloads / name, **kwargs)
