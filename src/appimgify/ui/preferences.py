"""Preferences, built as a standard ``AdwPreferencesWindow``."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gtk

from ..metadata.extractor import extraction_method_available
from ..persistence.config import Settings
from ..services.library_service import LibraryService
from ..utils.errors import AppimgifyError
from ..utils.paths import (
    config_dir,
    contract_user,
    default_appimage_dir,
    default_launcher_dir,
)
from . import dialogs

_COLOR_SCHEME_LABELS = (("system", "System"), ("light", "Light"), ("dark", "Dark"))

_DUPLICATE_LABELS = (
    ("ask", "Ask what to do"),
    ("import-anyway", "Add as a separate application"),
    ("replace", "Update the existing application"),
)


class PreferencesWindow(Adw.PreferencesWindow):
    """Every setting the application has, in two pages."""

    __gtype_name__ = "AppimgifyPreferencesWindow"

    def __init__(self, service: LibraryService) -> None:
        super().__init__()
        self._service = service
        self._settings = Settings(**vars(service.settings))
        self._loading = True

        self.set_search_enabled(True)
        self.add(self._build_storage_page())
        self.add(self._build_behaviour_page())
        self._loading = False

    # ------------------------------------------------------------------
    def _build_storage_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Storage", icon_name="folder-symbolic")

        appimage_group = Adw.PreferencesGroup(
            title="AppImage Storage",
            description="Where imported AppImages are kept. Existing applications "
            "stay where they are; only new imports use a changed location.",
        )
        self._appimage_row = self._path_row(
            "AppImage Folder",
            self._settings.appimage_path,
            self._choose_appimage_dir,
            self._reset_appimage_dir,
        )
        appimage_group.add(self._appimage_row)
        page.add(appimage_group)

        launcher_group = Adw.PreferencesGroup(
            title="Launcher Storage",
            description="Generated launchers are installed here. The default is the "
            "standard user application folder, which every desktop environment reads.",
        )
        self._launcher_row = self._path_row(
            "Launcher Folder",
            self._settings.launcher_path,
            self._choose_launcher_dir,
            self._reset_launcher_dir,
        )
        launcher_group.add(self._launcher_row)
        page.add(launcher_group)

        info_group = Adw.PreferencesGroup(title="Details")
        method = extraction_method_available()
        metadata_row = Adw.ActionRow(
            title="Metadata Extraction",
            subtitle="Reading AppImages directly with unsquashfs"
            if method == "unsquashfs"
            else "Using each AppImage’s own runtime — install “squashfs-tools” "
            "for faster, safer extraction",
        )
        metadata_row.add_css_class("property")
        info_group.add(metadata_row)

        config_row = Adw.ActionRow(
            title="Configuration Files", subtitle=contract_user(config_dir())
        )
        config_row.add_css_class("property")
        info_group.add(config_row)
        page.add(info_group)
        return page

    def _build_behaviour_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Behaviour", icon_name="preferences-system-symbolic")

        import_group = Adw.PreferencesGroup(
            title="Import", description="What happens when an AppImage is added"
        )

        self._create_launcher_row = Adw.SwitchRow(
            title="Create a Launcher Automatically",
            subtitle="Add the application to the applications menu on import",
            active=self._settings.create_launcher_on_import,
        )
        self._create_launcher_row.connect("notify::active", self._on_changed)
        import_group.add(self._create_launcher_row)

        self._extract_icon_row = Adw.SwitchRow(
            title="Extract the Icon Automatically",
            subtitle="Use the icon bundled inside the AppImage when there is one",
            active=self._settings.extract_icon_on_import,
        )
        self._extract_icon_row.connect("notify::active", self._on_changed)
        import_group.add(self._extract_icon_row)

        self._duplicate_row = Adw.ComboRow(
            title="When an Application Already Exists",
            model=Gtk.StringList.new([label for _value, label in _DUPLICATE_LABELS]),
            selected=_index_of(_DUPLICATE_LABELS, self._settings.duplicate_action),
        )
        self._duplicate_row.connect("notify::selected", self._on_changed)
        import_group.add(self._duplicate_row)

        self._launch_after_row = Adw.SwitchRow(
            title="Launch After Importing",
            active=self._settings.launch_after_import,
        )
        self._launch_after_row.connect("notify::active", self._on_changed)
        import_group.add(self._launch_after_row)
        page.add(import_group)

        removal_group = Adw.PreferencesGroup(title="Removal")
        self._confirm_removal_row = Adw.SwitchRow(
            title="Confirm Before Removing",
            subtitle="Ask what to delete before removing an application",
            active=self._settings.confirm_removal,
        )
        self._confirm_removal_row.connect("notify::active", self._on_changed)
        removal_group.add(self._confirm_removal_row)
        page.add(removal_group)

        appearance_group = Adw.PreferencesGroup(title="Appearance")
        self._color_scheme_row = Adw.ComboRow(
            title="Style",
            model=Gtk.StringList.new([label for _value, label in _COLOR_SCHEME_LABELS]),
            selected=_index_of(_COLOR_SCHEME_LABELS, self._settings.color_scheme),
        )
        self._color_scheme_row.connect("notify::selected", self._on_color_scheme_changed)
        appearance_group.add(self._color_scheme_row)
        page.add(appearance_group)
        return page

    # ------------------------------------------------------------------
    def _path_row(
        self,
        title: str,
        path: Path,
        choose: object,
        reset: object,
    ) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=contract_user(path), activatable=True)

        reset_button = Gtk.Button(
            icon_name="edit-undo-symbolic",
            tooltip_text="Use the default location",
            valign=Gtk.Align.CENTER,
        )
        reset_button.add_css_class("flat")
        reset_button.connect("clicked", lambda _button: reset())
        row.add_suffix(reset_button)

        choose_button = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text="Choose a folder",
            valign=Gtk.Align.CENTER,
        )
        choose_button.add_css_class("flat")
        choose_button.connect("clicked", lambda _button: choose())
        row.add_suffix(choose_button)
        row.set_activatable_widget(choose_button)
        return row

    def _choose_appimage_dir(self) -> None:
        dialogs.select_folder(
            self,
            "Choose the AppImage Folder",
            self._set_appimage_dir,
            initial_folder=self._settings.appimage_path,
        )

    def _set_appimage_dir(self, path: Path) -> None:
        self._settings.appimage_dir = str(path)
        self._appimage_row.set_subtitle(contract_user(path))
        self._apply()

    def _reset_appimage_dir(self) -> None:
        self._settings.appimage_dir = ""
        self._appimage_row.set_subtitle(contract_user(default_appimage_dir()))
        self._apply()

    def _choose_launcher_dir(self) -> None:
        dialogs.select_folder(
            self,
            "Choose the Launcher Folder",
            self._set_launcher_dir,
            initial_folder=self._settings.launcher_path,
        )

    def _set_launcher_dir(self, path: Path) -> None:
        if path != default_launcher_dir():
            dialogs.confirm(
                self,
                "Use a Non-Standard Launcher Folder?",
                "Most desktop environments only look for launchers in "
                f"“{contract_user(default_launcher_dir())}”. Launchers written "
                "elsewhere may not appear in your applications menu.",
                confirm_label="_Use It Anyway",
                on_confirm=lambda: self._commit_launcher_dir(path),
            )
            return
        self._commit_launcher_dir(path)

    def _commit_launcher_dir(self, path: Path) -> None:
        self._settings.launcher_dir = str(path)
        self._launcher_row.set_subtitle(contract_user(path))
        self._apply()

    def _reset_launcher_dir(self) -> None:
        self._settings.launcher_dir = ""
        self._launcher_row.set_subtitle(contract_user(default_launcher_dir()))
        self._apply()

    # ------------------------------------------------------------------
    def _on_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._settings.create_launcher_on_import = self._create_launcher_row.get_active()
        self._settings.extract_icon_on_import = self._extract_icon_row.get_active()
        self._settings.launch_after_import = self._launch_after_row.get_active()
        self._settings.confirm_removal = self._confirm_removal_row.get_active()
        self._settings.duplicate_action = _DUPLICATE_LABELS[
            self._duplicate_row.get_selected()
        ][0]
        self._apply()

    def _on_color_scheme_changed(self, *_args: object) -> None:
        if self._loading:
            return
        value = _COLOR_SCHEME_LABELS[self._color_scheme_row.get_selected()][0]
        self._settings.color_scheme = value
        apply_color_scheme(value)
        self._apply()

    def _apply(self) -> None:
        """Save immediately — Preferences windows in GNOME have no OK button."""
        try:
            self._service.update_settings(Settings(**vars(self._settings)))
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)


def apply_color_scheme(value: str) -> None:
    """Point ``AdwStyleManager`` at the requested scheme."""
    manager = Adw.StyleManager.get_default()
    manager.set_color_scheme(
        {
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }.get(value, Adw.ColorScheme.DEFAULT)
    )


def _index_of(pairs: tuple[tuple[str, str], ...], value: str) -> int:
    for index, (candidate, _label) in enumerate(pairs):
        if candidate == value:
            return index
    return 0
