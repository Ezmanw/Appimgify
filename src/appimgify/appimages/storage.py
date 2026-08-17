"""The managed AppImage store.

Layout, mirroring the documented structure::

    ~/.local/share/appimages/
    ├── ExampleApp/
    │   ├── ExampleApp.AppImage
    │   └── icon.png
    └── AnotherApp/
        └── AnotherApp.AppImage

One directory per application keeps the AppImage, its icon and any future
per-application data together, and makes removal a single, obvious operation.
Everything happens inside the user's home directory; no operation here needs
elevated privileges.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..utils.errors import StorageError
from ..utils.fileutils import (
    CancelCallback,
    ProgressCallback,
    copy_file,
    make_executable,
    prune_empty_dirs,
    remove_tree,
)
from ..utils.paths import ensure_dir, is_within, slugify, unique_path


class AppImageStore:
    """Owns the directory tree that holds every managed AppImage."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def set_root(self, root: Path) -> None:
        self._root = Path(root)

    # ------------------------------------------------------------------
    # Preconditions
    # ------------------------------------------------------------------
    def ensure_ready(self) -> Path:
        """Create the store if needed and confirm it is writable.

        Raises:
            StorageError: when the location cannot be used, with text that
                names the directory so the user can fix it in Preferences.
        """
        try:
            ensure_dir(self._root)
        except OSError as error:
            raise StorageError(
                "AppImage folder is unavailable",
                f"“{self._root}” could not be created: {error.strerror or error}. "
                "Choose a different location in Preferences.",
            ) from error
        if not os.access(str(self._root), os.W_OK | os.X_OK):
            raise StorageError(
                "AppImage folder is not writable",
                f"Appimgify cannot write to “{self._root}”. Choose a different "
                "location in Preferences.",
            )
        return self._root

    def free_space(self) -> int | None:
        """Bytes available in the store, or ``None`` if that is unknown."""
        try:
            usage = os.statvfs(str(self._root))
        except OSError:
            return None
        return usage.f_bavail * usage.f_frsize

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------
    def directory_name_for(self, app_name: str) -> str:
        return slugify(app_name, fallback="AppImage")

    def existing_directory(self, app_name: str) -> Path | None:
        """The store directory for ``app_name`` if it is already taken."""
        candidate = self._root / self.directory_name_for(app_name)
        return candidate if candidate.exists() else None

    def allocate_directory(self, app_name: str, *, reuse: bool = False) -> Path:
        """Reserve a directory for an application.

        With ``reuse=False`` an unused name is chosen (``App``, ``App-2``, …)
        so an import can never land on top of another application's files.
        """
        self.ensure_ready()
        stem = self.directory_name_for(app_name)
        target = self._root / stem if reuse else unique_path(self._root, stem)
        try:
            ensure_dir(target)
        except OSError as error:
            raise StorageError(
                "Application folder could not be created",
                f"“{target}” could not be created: {error.strerror or error}.",
            ) from error
        return target

    def appimage_target(self, directory: Path, source_name: str) -> Path:
        """Where a source file should be stored, keeping its original name."""
        name = Path(source_name).name or "Application.AppImage"
        if not name.lower().endswith(".appimage"):
            name = f"{name}.AppImage"
        return directory / name

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def store(
        self,
        source: Path,
        directory: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> Path:
        """Copy ``source`` into ``directory`` and make it executable."""
        target = self.appimage_target(directory, source.name)
        self._copy(source, target, progress=progress, cancelled=cancelled)
        return target

    def replace(
        self,
        source: Path,
        current: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> Path:
        """Swap a managed AppImage for a newer file.

        The replacement is written to a temporary name in the same directory
        and only moved into place once it has been copied in full, so a failed
        or cancelled update leaves the working AppImage untouched.
        """
        directory = current.parent
        staged = unique_path(directory, f".incoming-{current.stem}", current.suffix)
        try:
            self._copy(source, staged, progress=progress, cancelled=cancelled)
            target = self.appimage_target(directory, source.name)
            os.replace(staged, target)
            make_executable(target)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
        if target != current:
            current.unlink(missing_ok=True)
        return target

    def _copy(
        self,
        source: Path,
        target: Path,
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCallback | None,
    ) -> None:
        try:
            copy_file(source, target, progress=progress, cancelled=cancelled)
            make_executable(target)
        except InterruptedError:
            target.unlink(missing_ok=True)
            raise
        except PermissionError as error:
            raise StorageError(
                "AppImage could not be copied",
                f"Permission denied while writing “{target}”: {error.strerror or error}.",
            ) from error
        except OSError as error:
            target.unlink(missing_ok=True)
            detail = error.strerror or str(error)
            if getattr(error, "errno", None) == 28:
                detail = "there is not enough free space in the AppImage folder"
            raise StorageError(
                "AppImage could not be copied", f"Copying to “{target}” failed: {detail}."
            ) from error

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------
    def remove_application(self, directory: Path) -> None:
        """Delete a managed application directory.

        Refuses to touch anything outside the store — the user's original
        downloads are never at risk, only the managed copy.
        """
        directory = Path(directory)
        if not is_within(directory, self._root) or directory == self._root:
            raise StorageError(
                "Refusing to delete that folder",
                f"“{directory}” is outside the managed AppImage folder, so "
                "Appimgify will not remove it.",
            )
        remove_tree(directory)
        prune_empty_dirs(directory.parent, self._root)

    def owns(self, path: Path) -> bool:
        """Whether ``path`` is a file Appimgify manages."""
        return is_within(path, self._root)
