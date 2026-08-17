"""Reading name, description, categories and icon out of an AppImage.

Two extraction strategies are used, in order of preference:

1. **Offline** — ``unsquashfs`` reads the SquashFS payload directly at the
   offset computed from the ELF header.  Nothing inside the AppImage is
   executed, which is the safer route for a file the user just downloaded.
2. **Runtime** — if ``unsquashfs`` is unavailable, the AppImage's own runtime
   is invoked with ``--appimage-extract``, the mechanism defined by the
   AppImage format itself.

Failure at any point is never fatal: the importer falls back to defaults
derived from the file name and the user fills in the rest.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..models.metadata import ExtractedMetadata
from ..utils.fileutils import make_executable
from . import desktop_parser

if TYPE_CHECKING:  # avoids a cycle: appimages imports the importer, which
    # imports this module for extraction.
    from ..appimages.validator import AppImageInfo

#: Extraction is bounded so a hostile or broken AppImage cannot hang the app.
EXTRACT_TIMEOUT_SECONDS = 90

#: Icon files are looked for in these places, best first.
_ICON_SUFFIXES = (".svg", ".svgz", ".png", ".xpm")

_ICON_DIR_PREFERENCE = (
    "scalable",
    "512x512",
    "256x256",
    "192x192",
    "128x128",
    "96x96",
    "64x64",
    "48x48",
    "32x32",
    "24x24",
    "16x16",
)


class ExtractionScratch:
    """A temporary directory holding one AppImage's unpacked payload.

    Used as a context manager so the (potentially large) extracted tree is
    always cleaned up, including when the import is cancelled.
    """

    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="appimgify-extract-")
        self.path = Path(self._temp.name)

    def __enter__(self) -> "ExtractionScratch":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        self._temp.cleanup()


def extraction_method_available() -> str:
    """Which strategy will be used — for display in Preferences."""
    return "unsquashfs" if shutil.which("unsquashfs") else "appimage-runtime"


def extract(info: "AppImageInfo", scratch: ExtractionScratch) -> ExtractedMetadata:
    """Extract everything we can from ``info`` into ``scratch``.

    The returned metadata always has usable values: when nothing could be read
    the application name falls back to a tidied version of the file name.
    """
    metadata = ExtractedMetadata()
    root: Path | None = None

    if info.supports_extraction:
        root = _extract_payload(info, scratch, metadata)
    else:
        metadata.note(
            "This AppImage format does not support metadata extraction, so the "
            "details below were guessed from the file name."
        )

    if root is not None:
        _read_desktop_entry(root, metadata)
        metadata.icon_source = _find_icon(root, metadata.icon_name)
        if metadata.icon_source is None:
            metadata.note("No icon was found inside this AppImage.")

    if not metadata.name:
        metadata.name = fallback_name(info.path)
    return metadata


def fallback_name(path: Path) -> str:
    """A presentable application name derived from the file name."""
    stem = path.name
    for suffix in (".AppImage", ".appimage", ".AppImage.bin"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        stem = path.stem
    for separator in ("_", "-", "."):
        stem = stem.replace(separator, " ")
    words = [word for word in stem.split() if not _looks_like_build_token(word)]
    cleaned = " ".join(words).strip()
    return cleaned or path.stem or "AppImage"


def _looks_like_build_token(word: str) -> bool:
    """Drop version and architecture noise such as ``x86_64`` or ``v1.2.3``."""
    lowered = word.lower()
    if lowered in ("x86", "x86 64", "x8664", "amd64", "i386", "i686", "aarch64", "arm64"):
        return True
    if lowered.startswith("v") and lowered[1:2].isdigit():
        return True
    return bool(lowered) and lowered[0].isdigit() and any(c.isdigit() for c in lowered)


# ----------------------------------------------------------------------
# Payload extraction
# ----------------------------------------------------------------------
def _extract_payload(
    info: "AppImageInfo", scratch: ExtractionScratch, metadata: ExtractedMetadata
) -> Path | None:
    if shutil.which("unsquashfs") and info.payload_offset:
        root = _extract_with_unsquashfs(info, scratch)
        if root is not None:
            return root
        metadata.note("The bundled payload could not be unpacked with unsquashfs.")
    root = _extract_with_runtime(info, scratch)
    if root is None:
        metadata.note(
            "Metadata could not be read from this AppImage. Install "
            "“squashfs-tools” for more reliable extraction."
        )
    return root


def _extract_with_unsquashfs(
    info: "AppImageInfo", scratch: ExtractionScratch
) -> Path | None:
    target = scratch.path / "payload"
    command = [
        "unsquashfs",
        "-o",
        str(info.payload_offset),
        "-d",
        str(target),
        "-no-progress",
        "-quiet",
        "-f",
        str(info.path),
        "/*.desktop",
        "/.DirIcon",
        "/*.png",
        "/*.svg",
        "/*.svgz",
        "/*.xpm",
        "/usr/share/icons",
        "/usr/share/applications",
        "/usr/share/metainfo",
    ]
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=EXTRACT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return target if target.is_dir() and any(target.iterdir()) else None


def _extract_with_runtime(
    info: "AppImageInfo", scratch: ExtractionScratch
) -> Path | None:
    """Ask the AppImage's own runtime to unpack itself.

    The AppImage is copied into the scratch directory first so the user's
    original file never has its permissions changed.
    """
    staged = scratch.path / "runtime.AppImage"
    try:
        shutil.copy2(info.path, staged)
        make_executable(staged)
    except OSError:
        return None

    workdir = scratch.path / "runtime-out"
    workdir.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        # Keep the runtime from trying to mount anything or phone home.
        "APPIMAGE_EXTRACT_AND_RUN": "1",
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", str(scratch.path)),
    }
    try:
        subprocess.run(  # noqa: S603 - documented AppImage extraction interface
            [str(staged), "--appimage-extract"],
            cwd=str(workdir),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=EXTRACT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        staged.unlink(missing_ok=True)

    root = workdir / "squashfs-root"
    return root if root.is_dir() and any(root.iterdir()) else None


# ----------------------------------------------------------------------
# Interpreting the payload
# ----------------------------------------------------------------------
def _read_desktop_entry(root: Path, metadata: ExtractedMetadata) -> None:
    entry = _find_desktop_entry(root)
    if entry is None:
        metadata.note("This AppImage does not contain a desktop entry.")
        return

    values = desktop_parser.parse(entry)
    if not values:
        metadata.note("The desktop entry inside this AppImage could not be read.")
        return

    metadata.name = desktop_parser.get_string(values, "Name")
    metadata.generic_name = desktop_parser.get_string(values, "GenericName")
    metadata.comment = desktop_parser.get_string(values, "Comment")
    metadata.categories = desktop_parser.get_list(values, "Categories")
    metadata.keywords = desktop_parser.get_list(values, "Keywords")
    metadata.mime_types = desktop_parser.get_list(values, "MimeType")
    metadata.terminal = desktop_parser.get_bool(values, "Terminal", False)
    metadata.startup_notify = desktop_parser.get_bool(values, "StartupNotify", True)
    metadata.icon_name = desktop_parser.get_string(values, "Icon")
    metadata.version = desktop_parser.get_string(
        values, "X-AppImage-Version"
    ) or desktop_parser.get_string(values, "X-AppImage-BuildId")
    metadata.arguments = _arguments_from_exec(desktop_parser.get_string(values, "Exec"))


def _find_desktop_entry(root: Path) -> Path | None:
    """Root-level entries win; bundled application entries are the fallback."""
    try:
        candidates = sorted(root.glob("*.desktop"))
    except OSError:
        candidates = []
    if not candidates:
        try:
            candidates = sorted((root / "usr" / "share" / "applications").glob("*.desktop"))
        except OSError:
            candidates = []
    for candidate in candidates:
        resolved = _resolve_inside(candidate, root)
        if resolved is not None and resolved.is_file():
            return resolved
    return None


def _arguments_from_exec(exec_value: str) -> list[str]:
    """Extra arguments from a bundled ``Exec``, minus program and field codes.

    The program itself is discarded: the launcher we generate always points at
    the managed AppImage, never at the path recorded inside the bundle.
    """
    if not exec_value:
        return []
    try:
        tokens = shlex.split(exec_value)
    except ValueError:
        return []
    return [
        token
        for token in tokens[1:]
        if not (len(token) == 2 and token.startswith("%"))
    ]


def _find_icon(root: Path, icon_name: str) -> Path | None:
    """Locate the best icon in an extracted payload."""
    candidates: list[Path] = []

    dir_icon = root / ".DirIcon"
    resolved_dir_icon = _resolve_inside(dir_icon, root)
    if resolved_dir_icon is not None and resolved_dir_icon.is_file():
        candidates.append(resolved_dir_icon)

    if icon_name:
        stem = Path(icon_name).stem if "/" in icon_name or "." in icon_name else icon_name
        candidates.extend(_theme_icons(root, stem))
        for suffix in _ICON_SUFFIXES:
            candidate = _resolve_inside(root / f"{stem}{suffix}", root)
            if candidate is not None and candidate.is_file():
                candidates.append(candidate)

    candidates.extend(_theme_icons(root, None))
    for suffix in _ICON_SUFFIXES:
        try:
            for candidate in sorted(root.glob(f"*{suffix}")):
                resolved = _resolve_inside(candidate, root)
                if resolved is not None and resolved.is_file():
                    candidates.append(resolved)
        except OSError:
            continue

    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def _theme_icons(root: Path, stem: str | None) -> list[Path]:
    """Icons from ``usr/share/icons``, largest/scalable first."""
    base = root / "usr" / "share" / "icons"
    if not base.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    try:
        for path in base.rglob("*"):
            if not path.is_file() and not path.is_symlink():
                continue
            if path.suffix.lower() not in _ICON_SUFFIXES:
                continue
            if stem is not None and path.stem != stem:
                continue
            resolved = _resolve_inside(path, root)
            if resolved is None or not resolved.is_file():
                continue
            found.append((_icon_rank(path), resolved))
    except OSError:
        return []
    found.sort(key=lambda item: item[0])
    return [path for _rank, path in found]


def _icon_rank(path: Path) -> int:
    parts = {part.lower() for part in path.parts}
    for index, preferred in enumerate(_ICON_DIR_PREFERENCE):
        if preferred in parts:
            return index
    return len(_ICON_DIR_PREFERENCE)


def _resolve_inside(path: Path, root: Path) -> Path | None:
    """Resolve symlinks, refusing anything that escapes the payload.

    AppImages routinely use ``.DirIcon`` as a symlink; a malicious bundle could
    point it at a file outside the extraction directory, so the resolved path
    is checked against ``root`` before it is ever read or copied.
    """
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
    except OSError:
        return None
    if resolved == root_resolved or root_resolved in resolved.parents:
        return resolved
    return None
