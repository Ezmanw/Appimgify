"""Shared primitives: paths, filesystem helpers and error types."""

from .errors import (
    AppimgifyError,
    DesktopEntryError,
    MetadataError,
    PersistenceError,
    StorageError,
    ValidationError,
)

__all__ = [
    "AppimgifyError",
    "DesktopEntryError",
    "MetadataError",
    "PersistenceError",
    "StorageError",
    "ValidationError",
]
