"""Installing, refreshing and removing generated launchers.

The generator (:mod:`appimgify.desktop.entry`) decides *what* a launcher looks
like; this module decides *where* it goes and keeps the desktop environment's
caches informed.  Splitting the two keeps the generator pure and leaves room
for other launcher formats later — anything implementing
:class:`LauncherBackend` can be plugged in beside this one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from ..models.managed_app import ManagedApp
from ..utils.errors import DesktopEntryError
from ..utils.fileutils import write_text_atomic
from . import entry as entry_module


class LauncherBackend(Protocol):
    """Minimal contract for a launcher format (currently: desktop entries)."""

    def install(self, app: ManagedApp) -> Path: ...

    def uninstall(self, app: ManagedApp) -> bool: ...


class DesktopEntryInstaller:
    """Writes freedesktop.org desktop entries into a user-local directory."""

    def __init__(self, launcher_dir: Path) -> None:
        self._launcher_dir = Path(launcher_dir)

    @property
    def launcher_dir(self) -> Path:
        return self._launcher_dir

    def target_for(self, app: ManagedApp) -> Path:
        return self._launcher_dir / entry_module.desktop_file_name(app)

    def install(self, app: ManagedApp) -> Path:
        """Generate and write ``app``'s launcher, returning its path.

        A launcher previously installed under a different file name (because
        the application was renamed) is removed so the menu never shows stale
        duplicates.
        """
        try:
            contents = entry_module.render(app)
        except ValueError as error:
            raise DesktopEntryError(
                "Launcher could not be generated",
                f"{error}. Check the application’s name and AppImage location.",
            ) from error

        target = self.target_for(app)
        try:
            self._launcher_dir.mkdir(parents=True, exist_ok=True)
            write_text_atomic(target, contents)
            target.chmod(0o755)
        except OSError as error:
            raise DesktopEntryError(
                "Launcher could not be saved",
                f"Writing “{target}” failed: {error.strerror or error}.",
            ) from error

        previous = app.desktop_entry
        if previous is not None and previous != target and previous.is_file():
            if self._is_managed_entry(previous, app.id):
                previous.unlink(missing_ok=True)

        self.refresh_database()
        return target

    def uninstall(self, app: ManagedApp) -> bool:
        """Remove ``app``'s launcher. Returns ``True`` if a file was deleted."""
        removed = False
        for candidate in {app.desktop_entry, self.target_for(app)}:
            if candidate is None or not candidate.is_file():
                continue
            if not self._is_managed_entry(candidate, app.id):
                continue
            try:
                candidate.unlink()
                removed = True
            except OSError as error:
                raise DesktopEntryError(
                    "Launcher could not be removed",
                    f"Deleting “{candidate}” failed: {error.strerror or error}.",
                ) from error
        if removed:
            self.refresh_database()
        return removed

    def refresh_database(self) -> None:
        """Ask the desktop environment to re-read the launcher directory.

        GNOME and COSMIC both watch the directory and pick changes up on their
        own; running ``update-desktop-database`` additionally refreshes the
        MIME cache for environments that rely on it.  A missing tool is not an
        error — the launcher is already on disk either way.
        """
        tool = shutil.which("update-desktop-database")
        if tool is None or not self._launcher_dir.is_dir():
            return
        try:
            subprocess.run(
                [tool, str(self._launcher_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return

    def find_orphans(self, known_ids: set[str]) -> list[Path]:
        """Launchers we generated whose library record no longer exists."""
        orphans: list[Path] = []
        if not self._launcher_dir.is_dir():
            return orphans
        try:
            candidates = sorted(self._launcher_dir.glob("*.desktop"))
        except OSError:
            return orphans
        for candidate in candidates:
            identifier = self._managed_id(candidate)
            if identifier is not None and identifier not in known_ids:
                orphans.append(candidate)
        return orphans

    @staticmethod
    def _managed_id(path: Path) -> str | None:
        """Return the Appimgify id recorded in a desktop file, if any."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if line.startswith(entry_module.TRACKING_KEY + "="):
                        return line.split("=", 1)[1].strip()
                    if line.startswith("[") and not line.startswith("[Desktop Entry]"):
                        break
        except OSError:
            return None
        return None

    @classmethod
    def _is_managed_entry(cls, path: Path, app_id: str) -> bool:
        """Only ever delete launchers this application generated."""
        return cls._managed_id(path) == app_id


def launch(app: ManagedApp, *, environment: dict[str, str] | None = None) -> None:
    """Start a managed AppImage detached from Appimgify.

    Raises:
        DesktopEntryError: if the AppImage is missing, not executable or the
            process could not be spawned.
    """
    target = app.appimage
    if not target.is_file():
        raise DesktopEntryError(
            "AppImage is missing",
            f"“{target}” no longer exists. Replace the AppImage or remove the entry.",
        )
    if not os.access(str(target), os.X_OK):
        raise DesktopEntryError(
            "AppImage is not executable",
            "Use “Rebuild Launcher” to restore the executable permission.",
        )

    working_directory = app.working_directory or str(target.parent)
    if not Path(working_directory).is_dir():
        working_directory = str(target.parent)

    try:
        subprocess.Popen(  # noqa: S603 - launching exactly what the user asked for
            [str(target), *app.arguments],
            cwd=working_directory,
            env={**os.environ, **(environment or {})},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise DesktopEntryError(
            "Application could not be started",
            f"Launching “{app.name}” failed: {error.strerror or error}.",
        ) from error
