"""AppImage detection and validation.

Validation is done by reading the file's header rather than by trusting the
extension, and — importantly — without executing the candidate file.  An
AppImage is an ELF binary whose bytes 8–10 hold the magic ``0x41 0x49`` (``AI``)
followed by the format revision:

* type 1 — ISO 9660 payload appended to the runtime;
* type 2 — SquashFS payload appended to the runtime.

Some perfectly working AppImages are built without the magic bytes, so a bare
ELF executable with an ``.AppImage`` name is accepted with a warning rather
than rejected outright.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.errors import ValidationError

ELF_MAGIC = b"\x7fELF"
APPIMAGE_MAGIC = b"AI"
APPIMAGE_MAGIC_OFFSET = 8

#: Below this size the file cannot contain a runtime plus a payload.
MINIMUM_SIZE = 8 * 1024

TYPE_UNKNOWN = 0
TYPE_ISO = 1
TYPE_SQUASHFS = 2


@dataclass
class AppImageInfo:
    """The outcome of inspecting a candidate file."""

    path: Path
    size: int
    appimage_type: int = TYPE_UNKNOWN
    has_magic: bool = False
    payload_offset: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def type_label(self) -> str:
        if self.appimage_type == TYPE_SQUASHFS:
            return "AppImage (type 2)"
        if self.appimage_type == TYPE_ISO:
            return "AppImage (type 1)"
        return "AppImage (unrecognised type)"

    @property
    def supports_extraction(self) -> bool:
        """Type 2 payloads are the ones we can read metadata out of."""
        return self.appimage_type == TYPE_SQUASHFS


def looks_like_appimage(path: Path) -> bool:
    """Cheap check used for drag-and-drop highlighting and file filters."""
    try:
        inspect(path)
    except ValidationError:
        return False
    return True


def inspect(path: Path) -> AppImageInfo:
    """Validate ``path`` and describe it.

    Raises:
        ValidationError: with user-presentable text when the file cannot be
            used as an AppImage.
    """
    path = Path(path)
    if not path.exists():
        raise ValidationError(
            "File not found", f"“{path}” does not exist or is no longer reachable."
        )
    if path.is_dir():
        raise ValidationError(
            "That is a folder",
            "Select a single AppImage file rather than a folder.",
        )
    if not path.is_file():
        raise ValidationError(
            "Not a regular file",
            f"“{path.name}” is not a regular file, so it cannot be an AppImage.",
        )

    try:
        size = path.stat().st_size
        with open(path, "rb") as stream:
            header = stream.read(64)
    except PermissionError as error:
        raise ValidationError(
            "File cannot be read",
            f"Appimgify is not allowed to read “{path.name}”: {error.strerror or error}.",
        ) from error
    except OSError as error:
        raise ValidationError(
            "File cannot be read",
            f"Reading “{path.name}” failed: {error.strerror or error}.",
        ) from error

    if size < MINIMUM_SIZE:
        raise ValidationError(
            "File is too small",
            f"“{path.name}” is only {size} bytes — it cannot contain an application.",
        )
    if not header.startswith(ELF_MAGIC):
        raise ValidationError(
            "Not an AppImage",
            f"“{path.name}” is not a Linux executable. AppImages are ELF binaries "
            "with an application bundled inside them.",
        )

    info = AppImageInfo(path=path, size=size)
    magic = header[APPIMAGE_MAGIC_OFFSET : APPIMAGE_MAGIC_OFFSET + 3]
    if magic[:2] == APPIMAGE_MAGIC and len(magic) == 3:
        info.has_magic = True
        info.appimage_type = magic[2]
        if info.appimage_type not in (TYPE_ISO, TYPE_SQUASHFS):
            info.warnings.append(
                f"This file reports AppImage format {info.appimage_type}, which "
                "Appimgify does not know. It will be managed, but metadata cannot "
                "be read from it."
            )
    else:
        info.appimage_type = TYPE_SQUASHFS if path.suffix.lower() == ".appimage" else TYPE_UNKNOWN
        info.warnings.append(
            "This executable does not carry the AppImage signature. It can still "
            "be managed, but Appimgify cannot confirm that it is an AppImage."
        )

    if info.appimage_type == TYPE_ISO:
        info.warnings.append(
            "Type 1 AppImages are an old format. Metadata and icons cannot be "
            "read from them, so you may need to fill those in yourself."
        )

    info.payload_offset = _elf_payload_offset(path)
    if info.payload_offset is None and info.appimage_type == TYPE_SQUASHFS:
        info.warnings.append("The bundled payload could not be located in this file.")
    return info


def _elf_payload_offset(path: Path) -> int | None:
    """Offset of the data appended after the ELF runtime.

    This is the end of the section header table — the same value the AppImage
    runtime reports through ``--appimage-offset``, computed here by reading the
    ELF header so nothing has to be executed.
    """
    try:
        with open(path, "rb") as stream:
            header = stream.read(64)
    except OSError:
        return None
    if len(header) < 64 or not header.startswith(ELF_MAGIC):
        return None

    elf_class = header[4]  # 1 = 32-bit, 2 = 64-bit
    endianness = "<" if header[5] == 1 else ">"
    try:
        if elf_class == 1:
            section_offset = struct.unpack_from(endianness + "I", header, 0x20)[0]
            entry_size = struct.unpack_from(endianness + "H", header, 0x2E)[0]
            count = struct.unpack_from(endianness + "H", header, 0x30)[0]
        elif elf_class == 2:
            section_offset = struct.unpack_from(endianness + "Q", header, 0x28)[0]
            entry_size = struct.unpack_from(endianness + "H", header, 0x3A)[0]
            count = struct.unpack_from(endianness + "H", header, 0x3C)[0]
        else:
            return None
    except struct.error:
        return None

    offset = section_offset + entry_size * count
    if offset <= 0 or offset >= path.stat().st_size:
        return None
    return offset
