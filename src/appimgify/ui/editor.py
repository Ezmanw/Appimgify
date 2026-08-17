"""The launcher editor, shared by the import flow and the library detail pane.

Built entirely from ``AdwPreferencesPage`` groups and stock rows, so it looks
and behaves like GNOME's own settings surfaces and inherits their keyboard
navigation and accessible labelling for free.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from gi.repository import Adw, GObject, Gtk

from ..models import categories as categories_module
from ..models.managed_app import ManagedApp
from ..models.preset import Preset
from ..utils.paths import contract_user, expand_user
from . import dialogs, iconview

ICON_PREVIEW_SIZE = 48


class AppEditor(Adw.Bin):
    """Edits a :class:`ManagedApp` in place and reports when it is dirty."""

    __gtype_name__ = "AppimgifyAppEditor"

    __gsignals__ = {
        # Any field changed — used to enable Save and warn before leaving.
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, *, show_storage_details: bool = True) -> None:
        super().__init__()
        self._app: ManagedApp | None = None
        self._icon_source: Path | None = None
        self._icon_cleared = False
        self._working_directory = ""
        self._presets: list[Preset] = []
        self._loading = False
        self._show_storage_details = show_storage_details

        self._page = Adw.PreferencesPage()
        self._build_basic_group()
        self._build_preset_group()
        self._build_categories_group()
        self._build_launch_group()
        self._build_advanced_group()
        self.set_child(self._page)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_basic_group(self) -> None:
        group = Adw.PreferencesGroup(title="Basic Information")

        self._icon_image = iconview.icon_image(None, ICON_PREVIEW_SIZE)
        self._icon_row = Adw.ActionRow(
            title="Icon",
            subtitle="No icon selected",
            activatable=True,
        )
        self._icon_row.add_prefix(self._icon_image)
        self._icon_row.set_tooltip_text("Choose an image file to use as this application’s icon")

        self._icon_clear_button = Gtk.Button(
            icon_name="edit-clear-symbolic",
            tooltip_text="Remove the icon",
            valign=Gtk.Align.CENTER,
        )
        self._icon_clear_button.add_css_class("flat")
        self._icon_clear_button.set_visible(False)
        self._icon_clear_button.connect("clicked", self._on_icon_cleared)
        self._icon_row.add_suffix(self._icon_clear_button)

        choose_button = Gtk.Button(
            icon_name="document-open-symbolic",
            tooltip_text="Choose an icon file",
            valign=Gtk.Align.CENTER,
        )
        choose_button.add_css_class("flat")
        choose_button.connect("clicked", lambda _button: self._choose_icon())
        self._icon_row.add_suffix(choose_button)
        self._icon_row.set_activatable_widget(choose_button)
        group.add(self._icon_row)

        self._name_row = Adw.EntryRow(title="Application Name")
        self._name_row.connect("changed", self._on_field_changed)
        group.add(self._name_row)

        self._generic_row = Adw.EntryRow(title="Generic Name")
        self._generic_row.set_tooltip_text(
            "A short generic description, such as “Web Browser”"
        )
        self._generic_row.connect("changed", self._on_field_changed)
        group.add(self._generic_row)

        self._description_row = Adw.EntryRow(title="Description")
        self._description_row.connect("changed", self._on_field_changed)
        group.add(self._description_row)

        self._version_row = Adw.EntryRow(title="Version")
        self._version_row.connect("changed", self._on_field_changed)
        group.add(self._version_row)

        self._page.add(group)

    def _build_preset_group(self) -> None:
        group = Adw.PreferencesGroup(
            title="Preset",
            description="Apply a saved set of launcher options",
        )
        self._preset_model = Gtk.StringList.new(["Custom"])
        self._preset_row = Adw.ComboRow(title="Preset", model=self._preset_model)
        self._preset_row.connect("notify::selected", self._on_preset_selected)
        group.add(self._preset_row)
        self._page.add(group)

    def _build_categories_group(self) -> None:
        group = Adw.PreferencesGroup(
            title="Categories",
            description="Where this application appears in the applications menu",
        )
        self._categories_row = Adw.ExpanderRow(title="Categories", subtitle="No categories")
        self._category_switches: dict[str, Adw.SwitchRow] = {}
        for value, label in categories_module.MAIN_CATEGORIES:
            row = Adw.SwitchRow(title=label)
            row.connect("notify::active", self._on_category_toggled)
            self._categories_row.add_row(row)
            self._category_switches[value] = row
        group.add(self._categories_row)
        self._page.add(group)

    def _build_launch_group(self) -> None:
        group = Adw.PreferencesGroup(
            title="Launch",
            description="How the application is started from the menu",
        )

        self._arguments_row = Adw.EntryRow(title="Command-Line Arguments")
        self._arguments_row.set_tooltip_text(
            "Arguments passed to the AppImage, quoted like a shell command"
        )
        self._arguments_row.connect("changed", self._on_arguments_changed)
        group.add(self._arguments_row)

        self._working_directory_row = Adw.ActionRow(
            title="Working Directory", subtitle="Alongside the AppImage"
        )
        self._working_directory_clear = Gtk.Button(
            icon_name="edit-clear-symbolic",
            tooltip_text="Use the default working directory",
            valign=Gtk.Align.CENTER,
        )
        self._working_directory_clear.add_css_class("flat")
        self._working_directory_clear.set_visible(False)
        self._working_directory_clear.connect("clicked", self._on_working_directory_cleared)
        self._working_directory_row.add_suffix(self._working_directory_clear)

        choose_folder = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text="Choose a working directory",
            valign=Gtk.Align.CENTER,
        )
        choose_folder.add_css_class("flat")
        choose_folder.connect("clicked", lambda _button: self._choose_working_directory())
        self._working_directory_row.add_suffix(choose_folder)
        self._working_directory_row.set_activatable_widget(choose_folder)
        group.add(self._working_directory_row)

        self._terminal_row = Adw.SwitchRow(
            title="Run in a Terminal",
            subtitle="For command-line applications",
        )
        self._terminal_row.connect("notify::active", self._on_field_changed)
        group.add(self._terminal_row)

        self._startup_row = Adw.SwitchRow(
            title="Startup Notification",
            subtitle="Show a loading cursor while the application starts",
        )
        self._startup_row.connect("notify::active", self._on_field_changed)
        group.add(self._startup_row)

        self._page.add(group)

    def _build_advanced_group(self) -> None:
        group = Adw.PreferencesGroup(
            title="Advanced",
            description="Desktop entry options for unusual applications",
        )

        self._keywords_row = Adw.EntryRow(title="Search Keywords")
        self._keywords_row.set_tooltip_text("Comma-separated words used by menu search")
        self._keywords_row.connect("changed", self._on_field_changed)
        group.add(self._keywords_row)

        self._launcher_name_row = Adw.EntryRow(title="Launcher File Name")
        self._launcher_name_row.set_tooltip_text(
            "Leave empty to name the launcher automatically"
        )
        self._launcher_name_row.connect("changed", self._on_field_changed)
        group.add(self._launcher_name_row)

        self._hidden_row = Adw.SwitchRow(
            title="Hide from the Applications Menu",
            subtitle="Keep the launcher installed but do not show it",
        )
        self._hidden_row.connect("notify::active", self._on_field_changed)
        group.add(self._hidden_row)

        self._single_window_row = Adw.SwitchRow(
            title="Single Main Window",
            subtitle="The application only ever opens one window",
        )
        self._single_window_row.connect("notify::active", self._on_field_changed)
        group.add(self._single_window_row)

        self._storage_row = Adw.ActionRow(
            title="AppImage Location", subtitle="Not stored yet"
        )
        self._storage_row.add_css_class("property")
        self._storage_row.set_visible(self._show_storage_details)
        group.add(self._storage_row)

        self._launcher_row = Adw.ActionRow(title="Launcher", subtitle="Not created yet")
        self._launcher_row.add_css_class("property")
        self._launcher_row.set_visible(self._show_storage_details)
        group.add(self._launcher_row)

        self._page.add(group)

    # ------------------------------------------------------------------
    # Loading and collecting
    # ------------------------------------------------------------------
    def load(
        self,
        app: ManagedApp,
        *,
        icon_source: Path | None = None,
        presets: list[Preset] | None = None,
    ) -> None:
        """Show ``app`` in the editor, discarding any unsaved edits."""
        self._loading = True
        self._app = app
        self._icon_source = icon_source
        self._icon_cleared = False
        self._working_directory = app.working_directory

        if presets is not None:
            self._set_presets(presets)

        self._name_row.set_text(app.name)
        self._generic_row.set_text(app.generic_name)
        self._description_row.set_text(app.description)
        self._version_row.set_text(app.version)
        self._arguments_row.set_text(app.arguments_text)
        self._keywords_row.set_text(", ".join(app.keywords))
        self._launcher_name_row.set_text(app.desktop_file_name)
        self._terminal_row.set_active(app.terminal)
        self._startup_row.set_active(app.startup_notify)
        self._hidden_row.set_active(app.no_display)
        self._single_window_row.set_active(app.single_main_window)

        selected = set(app.categories)
        for value, row in self._category_switches.items():
            row.set_active(value in selected)

        self._preset_row.set_selected(0)
        self._refresh_icon()
        self._refresh_working_directory()
        self._refresh_categories_subtitle()
        self._refresh_paths()
        self._loading = False

    def collect(self) -> ManagedApp:
        """Return a copy of the loaded application with the edited values.

        Raises:
            ValueError: if a field cannot be interpreted; the message is
                suitable for showing directly to the user.
        """
        if self._app is None:
            raise ValueError("No application is being edited.")

        name = self._name_row.get_text().strip()
        if not name:
            raise ValueError("The application needs a name.")

        arguments = self.parsed_arguments()
        icon_path = self._app.icon_path
        if self._icon_cleared:
            icon_path = ""

        return self._app.copy_with(
            name=name,
            generic_name=self._generic_row.get_text().strip(),
            description=self._description_row.get_text().strip(),
            version=self._version_row.get_text().strip(),
            categories=[
                value
                for value, row in self._category_switches.items()
                if row.get_active()
            ],
            arguments=arguments,
            keywords=[
                keyword.strip()
                for keyword in self._keywords_row.get_text().split(",")
                if keyword.strip()
            ],
            working_directory=self._working_directory,
            terminal=self._terminal_row.get_active(),
            startup_notify=self._startup_row.get_active(),
            no_display=self._hidden_row.get_active(),
            single_main_window=self._single_window_row.get_active(),
            desktop_file_name=self._launcher_name_row.get_text().strip(),
            icon_path=icon_path,
        )

    def parsed_arguments(self) -> list[str]:
        text = self._arguments_row.get_text().strip()
        if not text:
            return []
        try:
            return shlex.split(text)
        except ValueError as error:
            raise ValueError(
                f"The command-line arguments could not be read: {error}."
            ) from error

    @property
    def pending_icon_source(self) -> Path | None:
        """An icon file the user picked that has not been stored yet."""
        return self._icon_source

    @property
    def icon_cleared(self) -> bool:
        return self._icon_cleared

    def focus_name(self) -> None:
        self._name_row.grab_focus()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _set_presets(self, presets: list[Preset]) -> None:
        self._presets = presets
        self._preset_model.splice(
            0, self._preset_model.get_n_items(), ["Custom", *(item.name for item in presets)]
        )

    def _on_preset_selected(self, *_args: object) -> None:
        if self._loading or self._app is None:
            return
        index = self._preset_row.get_selected()
        if index <= 0 or index > len(self._presets):
            return
        preset = self._presets[index - 1]
        self._loading = True
        for value, row in self._category_switches.items():
            row.set_active(value in preset.categories)
        self._arguments_row.set_text(
            " ".join(shlex.quote(argument) for argument in preset.arguments)
        )
        self._terminal_row.set_active(preset.terminal)
        self._startup_row.set_active(preset.startup_notify)
        if preset.working_directory:
            self._working_directory = preset.working_directory
            self._refresh_working_directory()
        self._refresh_categories_subtitle()
        self._loading = False
        self._on_field_changed()

    # ------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------
    def _choose_icon(self) -> None:
        window = self.get_root()
        if not isinstance(window, Gtk.Window):
            return
        dialogs.open_file(
            window,
            "Choose an Icon",
            dialogs.image_filters(),
            self._set_icon_source,
        )

    def _set_icon_source(self, path: Path) -> None:
        self._icon_source = path
        self._icon_cleared = False
        self._refresh_icon()
        self._on_field_changed()

    def _on_icon_cleared(self, _button: Gtk.Button) -> None:
        self._icon_source = None
        self._icon_cleared = True
        self._refresh_icon()
        self._on_field_changed()

    def _refresh_icon(self) -> None:
        path: Path | None = None
        subtitle = "No icon — the system’s generic icon will be used"
        if self._icon_source is not None:
            path = self._icon_source
            subtitle = f"Selected file: {contract_user(self._icon_source)}"
        elif not self._icon_cleared and self._app is not None and self._app.icon_exists():
            path = self._app.icon
            subtitle = "Stored with this application"
        elif not self._icon_cleared and self._app is not None and self._app.icon_path:
            subtitle = "The stored icon file is missing"

        iconview.apply_icon(self._icon_image, path)
        self._icon_row.set_subtitle(subtitle)
        self._icon_clear_button.set_visible(path is not None)

    # ------------------------------------------------------------------
    # Working directory
    # ------------------------------------------------------------------
    def _choose_working_directory(self) -> None:
        window = self.get_root()
        if not isinstance(window, Gtk.Window):
            return
        dialogs.select_folder(
            window,
            "Choose a Working Directory",
            self._set_working_directory,
            initial_folder=expand_user(self._working_directory)
            if self._working_directory
            else None,
        )

    def _set_working_directory(self, path: Path) -> None:
        self._working_directory = str(path)
        self._refresh_working_directory()
        self._on_field_changed()

    def _on_working_directory_cleared(self, _button: Gtk.Button) -> None:
        self._working_directory = ""
        self._refresh_working_directory()
        self._on_field_changed()

    def _refresh_working_directory(self) -> None:
        if self._working_directory:
            self._working_directory_row.set_subtitle(contract_user(self._working_directory))
        else:
            self._working_directory_row.set_subtitle("Alongside the AppImage")
        self._working_directory_clear.set_visible(bool(self._working_directory))

    # ------------------------------------------------------------------
    # Change tracking
    # ------------------------------------------------------------------
    def _on_field_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self.emit("changed")

    def _on_category_toggled(self, *_args: object) -> None:
        self._refresh_categories_subtitle()
        self._on_field_changed()

    def _on_arguments_changed(self, *_args: object) -> None:
        try:
            self.parsed_arguments()
        except ValueError:
            self._arguments_row.add_css_class("error")
        else:
            self._arguments_row.remove_css_class("error")
        self._on_field_changed()

    def _refresh_categories_subtitle(self) -> None:
        selected = [
            value for value, row in self._category_switches.items() if row.get_active()
        ]
        self._categories_row.set_subtitle(categories_module.describe(selected))

    def _refresh_paths(self) -> None:
        if self._app is None:
            return
        self._storage_row.set_subtitle(
            contract_user(self._app.appimage_path)
            if self._app.appimage_path
            else "Not stored yet"
        )
        self._launcher_row.set_subtitle(
            contract_user(self._app.desktop_entry_path)
            if self._app.desktop_entry_path
            else "Not created yet"
        )
