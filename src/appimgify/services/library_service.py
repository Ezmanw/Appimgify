"""The single façade the user interface talks to.

Widgets never touch the store, the library file or the launcher installer
directly; they call this service and listen to its signals.  That keeps the UI
free of filesystem logic and means the whole application state can be driven
from a test without a display.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gi.repository import GObject

from ..appimages.importer import AppImageImporter, ImportDraft
from ..appimages.storage import AppImageStore
from ..desktop import installer as installer_module
from ..desktop.installer import DesktopEntryInstaller
from ..metadata import icons as icons_module
from ..models.managed_app import ManagedApp
from ..models.preset import Preset
from ..persistence.config import Settings, SettingsStore
from ..persistence.library import Library
from ..persistence.presets_store import PresetStore
from ..utils.errors import AppimgifyError, StorageError
from ..utils.fileutils import CancelCallback, ProgressCallback, make_executable


class Health(Enum):
    """How usable a managed application currently is."""

    OK = "ok"
    MISSING_APPIMAGE = "missing-appimage"
    NOT_EXECUTABLE = "not-executable"
    MISSING_LAUNCHER = "missing-launcher"
    MISSING_ICON = "missing-icon"

    @property
    def is_problem(self) -> bool:
        return self is not Health.OK


@dataclass(frozen=True)
class RemovalOptions:
    """What a removal should actually delete."""

    remove_appimage: bool = True
    remove_launcher: bool = True


class LibraryService(GObject.GObject):
    """Owns application state and exposes every operation the UI needs."""

    __gsignals__ = {
        # The set of applications changed (added, removed, reloaded).
        "library-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # One application's record changed; argument is its id.
        "app-updated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # Settings were saved.
        "settings-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # A recoverable problem worth telling the user about.
        "notice": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        settings_store: SettingsStore | None = None,
        library: Library | None = None,
        preset_store: PresetStore | None = None,
    ) -> None:
        super().__init__()
        self._settings_store = settings_store or SettingsStore()
        self._library = library or Library()
        self._presets = preset_store or PresetStore()
        self._settings = Settings()
        self._store = AppImageStore(self._settings.appimage_path)
        self._installer = DesktopEntryInstaller(self._settings.launcher_path)
        self._importer = AppImageImporter(self._store, self._installer)

    # ------------------------------------------------------------------
    # Start-up
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Read settings, library and presets, reporting recovered damage."""
        self._settings = self._settings_store.load()
        self._apply_settings_paths()
        self._library.load()
        self._presets.load()
        self.emit("library-changed")

        if self._settings_store.recovered_from_corruption:
            self.emit(
                "notice",
                "Your settings file could not be read and was reset. "
                "The damaged file was kept alongside it.",
            )
        if self._library.recovered_from_corruption:
            self.emit(
                "notice",
                "The application library could not be read and was reset. "
                "The damaged file was kept alongside it.",
            )
        elif self._library.skipped_records:
            count = self._library.skipped_records
            self.emit(
                "notice",
                f"{count} damaged entr{'y was' if count == 1 else 'ies were'} "
                "skipped while loading the library.",
            )
        if self._presets.recovered_from_corruption:
            self.emit("notice", "Your presets file could not be read and was reset.")

    def _apply_settings_paths(self) -> None:
        self._store.set_root(self._settings.appimage_path)
        self._installer = DesktopEntryInstaller(self._settings.launcher_path)
        self._importer = AppImageImporter(self._store, self._installer)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def store(self) -> AppImageStore:
        return self._store

    @property
    def installer(self) -> DesktopEntryInstaller:
        return self._installer

    @property
    def importer(self) -> AppImageImporter:
        return self._importer

    @property
    def apps(self) -> list[ManagedApp]:
        return self._library.apps

    def get(self, app_id: str) -> ManagedApp | None:
        return self._library.get(app_id)

    def presets(self) -> list[Preset]:
        return self._presets.all()

    def save_preset(self, preset: Preset) -> Preset:
        return self._presets.add(preset)

    def remove_preset(self, preset_id: str) -> bool:
        return self._presets.remove(preset_id)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def update_settings(self, settings: Settings) -> None:
        """Persist new preferences and re-point the store and installer."""
        self._settings = settings
        self._settings_store.save(settings)
        self._apply_settings_paths()
        self.emit("settings-changed")

    def save_window_state(self, width: int, height: int, maximized: bool) -> None:
        self._settings.window_width = width
        self._settings.window_height = height
        self._settings.window_maximized = maximized
        try:
            self._settings_store.save(self._settings)
        except AppimgifyError:
            pass  # window geometry is never worth interrupting the user for

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def filtered(
        self, query: str = "", category: str = "", sort_order: str | None = None
    ) -> list[ManagedApp]:
        """Search, filter by category and sort in one place.

        Kept in the service so the list view stays a plain renderer.
        """
        apps = [app for app in self._library if app.matches(query)]
        if category:
            apps = [app for app in apps if category in app.categories]
        order = sort_order or self._settings.sort_order
        if order == "recent":
            apps.sort(key=lambda app: app.imported_at, reverse=True)
        elif order == "category":
            apps.sort(
                key=lambda app: (
                    app.categories[0] if app.categories else "￿",
                    app.name.casefold(),
                )
            )
        else:
            apps.sort(key=lambda app: app.name.casefold())
        return apps

    def used_categories(self) -> list[str]:
        """Categories that at least one managed application uses."""
        from ..models import categories as categories_module

        used = {value for app in self._library for value in app.categories}
        return [value for value, _label in categories_module.MAIN_CATEGORIES if value in used]

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def prepare_import(self, source: Path) -> ImportDraft:
        """Validate and inspect a file. Runs on a worker thread."""
        self._store.ensure_ready()
        draft = self._importer.prepare(source, self._library.apps)
        if not self._settings.extract_icon_on_import:
            draft.icon_source = None
        return draft

    def commit_import(
        self,
        draft: ImportDraft,
        app: ManagedApp,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> ManagedApp:
        """Install a prepared draft. Runs on a worker thread."""
        result = self._importer.commit(
            draft,
            app,
            create_launcher=self._settings.create_launcher_on_import,
            progress=progress,
            cancelled=cancelled,
        )
        self._library.add(result)
        return result

    def notify_library_changed(self) -> None:
        """Emitted by the UI once a worker thread's result has been stored."""
        self.emit("library-changed")

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def apply_changes(self, app: ManagedApp, *, icon_source: Path | None = None) -> ManagedApp:
        """Save an edited application and regenerate its launcher."""
        from ..utils.fileutils import remove_tree

        updated = app
        if icon_source is not None:
            stored_icon = icons_module.install(icon_source, updated.storage_dir)
            updated = updated.copy_with(icon_path=str(stored_icon))
        elif not updated.icon_path:
            # The icon was cleared in the editor — drop the stored file too.
            for existing in icons_module.stored_icons(updated.storage_dir):
                remove_tree(existing)
        entry_path = self._installer.install(updated)
        updated = updated.copy_with(desktop_entry_path=str(entry_path))
        self._library.update(updated)
        self.emit("app-updated", updated.id)
        self.emit("library-changed")
        return updated

    def clear_icon(self, app: ManagedApp) -> ManagedApp:
        """Drop the stored icon, falling back to the system's generic one."""
        return self.apply_changes(app.copy_with(icon_path=""))

    def rebuild_launcher(self, app: ManagedApp) -> ManagedApp:
        """Regenerate the desktop entry and repair the executable bit."""
        if not app.appimage_exists():
            raise StorageError(
                "AppImage is missing",
                f"“{app.appimage_path}” no longer exists, so its launcher cannot "
                "be rebuilt. Replace the AppImage or remove this application.",
            )
        try:
            make_executable(app.appimage)
        except OSError as error:
            raise StorageError(
                "Permission could not be set",
                f"“{app.appimage_path}” could not be made executable: "
                f"{error.strerror or error}.",
            ) from error
        return self.apply_changes(app)

    def replace_appimage(
        self,
        app: ManagedApp,
        source: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> ManagedApp:
        """Update an application to a newer AppImage. Runs on a worker thread."""
        updated = self._importer.replace(
            app, source, progress=progress, cancelled=cancelled
        )
        entry_path = self._installer.install(updated)
        updated = updated.copy_with(desktop_entry_path=str(entry_path))
        self._library.update(updated)
        return updated

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------
    def remove(self, app: ManagedApp, options: RemovalOptions) -> None:
        """Remove an application according to ``options``.

        The library record is dropped whenever the AppImage is removed; keeping
        a record that points at nothing would only produce a broken entry.
        """
        problems: list[str] = []
        if options.remove_launcher:
            try:
                self._installer.uninstall(app)
            except AppimgifyError as error:
                problems.append(error.detail or error.title)

        if options.remove_appimage:
            if self._store.owns(app.appimage):
                try:
                    self._store.remove_application(app.storage_dir)
                except AppimgifyError as error:
                    problems.append(error.detail or error.title)
            else:
                problems.append(
                    "The AppImage is stored outside the managed folder, so it was left "
                    "in place."
                )
            self._library.remove(app.id)
        else:
            self._library.update(app.copy_with(desktop_entry_path=""))

        self.emit("library-changed")
        for problem in problems:
            self.emit("notice", problem)

    # ------------------------------------------------------------------
    # Launching and inspection
    # ------------------------------------------------------------------
    def launch(self, app: ManagedApp) -> None:
        installer_module.launch(app)

    def health(self, app: ManagedApp) -> Health:
        """The first problem an application has, in order of severity."""
        if not app.appimage_exists():
            return Health.MISSING_APPIMAGE
        if not os.access(app.appimage_path, os.X_OK):
            return Health.NOT_EXECUTABLE
        if not app.launcher_exists():
            return Health.MISSING_LAUNCHER
        if app.icon_path and not app.icon_exists():
            return Health.MISSING_ICON
        return Health.OK

    def health_message(self, health: Health) -> str:
        return {
            Health.OK: "",
            Health.MISSING_APPIMAGE: "The AppImage file is missing",
            Health.NOT_EXECUTABLE: "The AppImage is not executable",
            Health.MISSING_LAUNCHER: "The launcher is missing from the applications menu",
            Health.MISSING_ICON: "The icon file is missing",
        }[health]

    def problems(self) -> list[tuple[ManagedApp, Health]]:
        """Every application that currently needs attention."""
        found = []
        for app in self._library:
            state = self.health(app)
            if state.is_problem:
                found.append((app, state))
        return found

    def orphaned_launchers(self) -> list[Path]:
        """Launchers we generated that no longer have a library record."""
        return self._installer.find_orphans(self._library.ids())

    def forget_orphans(self) -> int:
        """Delete leftover launchers, returning how many were removed."""
        removed = 0
        for path in self.orphaned_launchers():
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        if removed:
            self._installer.refresh_database()
        return removed
