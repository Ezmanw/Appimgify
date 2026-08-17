"""The import pipeline: validate → inspect → stage → install.

Importing is split into two phases so the user interface can put an editor in
between them:

* :meth:`AppImageImporter.prepare` validates the file and reads whatever
  metadata it can, producing an :class:`ImportDraft` that nothing on disk
  depends on yet;
* :meth:`AppImageImporter.commit` copies the AppImage into the store, stores
  the icon and generates the launcher.

Nothing is written outside the scratch directory until ``commit`` runs, so
cancelling at the editor stage leaves the system exactly as it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..desktop.installer import DesktopEntryInstaller
from ..metadata import extractor
from ..metadata import icons as icons_module
from ..metadata.extractor import ExtractionScratch
from ..models.managed_app import ManagedApp
from ..models.metadata import ExtractedMetadata
from ..utils.errors import ImportError_, StorageError, ValidationError
from ..utils.fileutils import CancelCallback, ProgressCallback
from ..utils.paths import slugify
from . import validator
from .storage import AppImageStore


@dataclass
class ImportDraft:
    """A validated, inspected AppImage that has not been installed yet."""

    source: Path
    info: validator.AppImageInfo
    metadata: ExtractedMetadata
    app: ManagedApp
    scratch: ExtractionScratch
    icon_source: Path | None = None
    #: Existing application this file appears to be a new version of.
    duplicate_of: ManagedApp | None = None
    warnings: list[str] = field(default_factory=list)

    def release(self) -> None:
        """Discard the extracted payload. Safe to call more than once."""
        self.scratch.cleanup()


class AppImageImporter:
    """Turns a file the user picked into a managed application."""

    def __init__(self, store: AppImageStore, installer: DesktopEntryInstaller) -> None:
        self._store = store
        self._installer = installer

    # ------------------------------------------------------------------
    # Phase 1 — inspect
    # ------------------------------------------------------------------
    def prepare(self, source: Path, existing: list[ManagedApp] | None = None) -> ImportDraft:
        """Validate ``source`` and build an editable draft.

        Raises:
            ValidationError: if the file is not a usable AppImage.
        """
        source = Path(source).expanduser()
        info = validator.inspect(source)

        scratch = ExtractionScratch()
        try:
            metadata = extractor.extract(info, scratch)
        except Exception:  # extraction must never break the import
            scratch.cleanup()
            raise
        if self._store.owns(source):
            scratch.cleanup()
            raise ValidationError(
                "Already managed",
                f"“{source.name}” is already stored in the managed AppImage folder. "
                "Use “Replace AppImage” on the application instead.",
            )

        app = ManagedApp(
            name=metadata.name or extractor.fallback_name(source),
            appimage_path="",
            generic_name=metadata.generic_name,
            description=metadata.comment,
            version=metadata.version,
            categories=_normalise_categories(metadata.categories),
            arguments=list(metadata.arguments),
            terminal=metadata.terminal,
            startup_notify=metadata.startup_notify,
            keywords=list(metadata.keywords),
            mime_types=list(metadata.mime_types),
            source_path=str(source),
        )
        draft = ImportDraft(
            source=source,
            info=info,
            metadata=metadata,
            app=app,
            scratch=scratch,
            icon_source=metadata.icon_source,
            warnings=[*info.warnings, *metadata.notes],
        )
        draft.duplicate_of = find_duplicate(app.name, source, existing or [])
        return draft

    # ------------------------------------------------------------------
    # Phase 2 — install
    # ------------------------------------------------------------------
    def commit(
        self,
        draft: ImportDraft,
        app: ManagedApp,
        *,
        create_launcher: bool = True,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> ManagedApp:
        """Store the AppImage described by ``draft`` using the edited ``app``.

        On any failure the partially created application directory is removed,
        so a failed import never leaves debris in the store.  The draft's
        extracted payload is only released on success — after a failure the
        caller can correct the problem and commit the same draft again.

        Raises:
            ImportError_: if the copy or launcher generation failed.
            StorageError: if the store is unusable.
        """
        self._store.ensure_ready()
        if not draft.source.is_file():
            raise ImportError_(
                "Source file is gone",
                f"“{draft.source}” could not be read any more. It may have been "
                "moved or deleted since it was selected.",
            )

        directory = self._store.allocate_directory(app.name)
        created_directory = directory
        try:
            stored = self._store.store(
                draft.source, directory, progress=progress, cancelled=cancelled
            )
            icon_path = self._store_icon(draft.icon_source, directory)
            result = app.copy_with(
                appimage_path=str(stored),
                icon_path=icon_path,
                source_path=str(draft.source),
            )
            if create_launcher:
                entry_path = self._installer.install(result)
                result = result.copy_with(desktop_entry_path=str(entry_path))
        except InterruptedError:
            self._store.remove_application(created_directory)
            raise
        except (StorageError, ImportError_):
            self._store.remove_application(created_directory)
            raise
        except OSError as error:
            self._store.remove_application(created_directory)
            raise ImportError_(
                "Import failed",
                f"“{app.name}” could not be installed: {error.strerror or error}.",
            ) from error
        except Exception:
            self._store.remove_application(created_directory)
            raise
        draft.release()
        return result

    # ------------------------------------------------------------------
    # Replacing an AppImage in place
    # ------------------------------------------------------------------
    def replace(
        self,
        app: ManagedApp,
        source: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> ManagedApp:
        """Update ``app`` to a newer AppImage, keeping its configuration.

        The new file is validated before anything is written, and the existing
        AppImage is only removed once the replacement is completely in place.
        """
        source = Path(source).expanduser()
        info = validator.inspect(source)
        if self._store.owns(source):
            raise ValidationError(
                "Choose a different file",
                "That file is already inside the managed AppImage folder.",
            )
        if not app.appimage_exists():
            raise StorageError(
                "Managed AppImage is missing",
                f"“{app.appimage_path}” no longer exists, so it cannot be replaced. "
                "Remove this application and import the new file instead.",
            )

        stored = self._store.replace(
            source, app.appimage, progress=progress, cancelled=cancelled
        )
        updated = app.copy_with(appimage_path=str(stored), source_path=str(source))

        version = _version_from(source, info)
        if version:
            updated = updated.copy_with(version=version)
        return updated

    # ------------------------------------------------------------------
    def _store_icon(self, icon_source: Path | None, directory: Path) -> str:
        """Copy the chosen icon into the application directory, if there is one."""
        if icon_source is None:
            return ""
        try:
            return str(icons_module.install(icon_source, directory))
        except StorageError:
            return ""  # an application without an icon is still perfectly usable


def find_duplicate(
    name: str, source: Path, existing: list[ManagedApp]
) -> ManagedApp | None:
    """Find an already-managed application this file probably belongs to."""
    slug = slugify(name).casefold()
    source_name = source.name.casefold()
    for candidate in existing:
        if candidate.name.casefold() == name.casefold():
            return candidate
        if slugify(candidate.name).casefold() == slug:
            return candidate
        if candidate.appimage_filename.casefold() == source_name:
            return candidate
    return None


def _normalise_categories(values: list[str]) -> list[str]:
    from ..models import categories as categories_module

    return categories_module.normalise(values)


def _version_from(source: Path, info: validator.AppImageInfo) -> str:
    """Best-effort version for a replacement, read from its own metadata."""
    scratch = ExtractionScratch()
    try:
        metadata = extractor.extract(info, scratch)
        return metadata.version
    except Exception:
        return ""
    finally:
        scratch.cleanup()
