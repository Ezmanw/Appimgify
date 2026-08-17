"""Error types carrying user-presentable text.

Every failure the user can plausibly cause (a bad file, a full disk, a
read-only directory) is reported through :class:`AppimgifyError`, which always
has a short ``title`` and a longer ``detail`` suitable for an ``AdwAlertDialog``.
"""

from __future__ import annotations


class AppimgifyError(Exception):
    """Base class for recoverable, user-facing errors."""

    def __init__(self, title: str, detail: str = "") -> None:
        super().__init__(f"{title}: {detail}" if detail else title)
        self.title = title
        self.detail = detail


class ValidationError(AppimgifyError):
    """The selected file is not a usable AppImage."""


class StorageError(AppimgifyError):
    """The managed AppImage directory could not be read or written."""


class ImportError_(AppimgifyError):
    """Copying an AppImage into the managed directory failed."""


class DesktopEntryError(AppimgifyError):
    """A desktop entry could not be generated or installed."""


class MetadataError(AppimgifyError):
    """Metadata could not be extracted (never fatal — always recoverable)."""


class PersistenceError(AppimgifyError):
    """The library or configuration file could not be read or written."""


class OperationCancelled(Exception):
    """Raised internally when the user cancels a long-running operation."""
