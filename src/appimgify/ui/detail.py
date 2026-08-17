"""The content pane: one application's launcher configuration and actions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from gi.repository import Adw, Gio, GObject, Gtk

from ..models.managed_app import ManagedApp
from ..models.preset import Preset
from ..services.library_service import Health, LibraryService, RemovalOptions
from ..utils.errors import AppimgifyError
from . import dialogs
from .editor import AppEditor
from .import_dialog import replace_appimage


class AppDetailPage(Adw.NavigationPage):
    """Shows and edits the selected application.

    Editing is explicit: the Save button only becomes sensitive once something
    changes, and navigating away with unsaved changes asks first.
    """

    __gtype_name__ = "AppimgifyAppDetailPage"

    __gsignals__ = {
        # The library changed as a result of an action taken here.
        "app-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "app-removed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, service: LibraryService) -> None:
        super().__init__(title="Application")
        self._service = service
        self._app: ManagedApp | None = None
        self._dirty = False

        self._editor = AppEditor(show_storage_details=True)
        self._editor.connect("changed", self._on_editor_changed)

        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._launch_button = Gtk.Button(
            child=Adw.ButtonContent(icon_name="media-playback-start-symbolic", label="Launch"),
            tooltip_text="Start this application",
        )
        self._launch_button.connect("clicked", lambda _button: self._launch())

        self._save_button = Gtk.Button(label="_Save", use_underline=True)
        self._save_button.add_css_class("suggested-action")
        self._save_button.set_sensitive(False)
        self._save_button.connect("clicked", lambda _button: self.save())

        menu_button = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            tooltip_text="Application options",
            menu_model=self._build_menu(),
        )

        self._header = Adw.HeaderBar()
        self._header.pack_start(self._launch_button)
        self._header.pack_end(self._save_button)
        self._header.pack_end(menu_button)

        self._banner = Adw.Banner(revealed=False)
        self._banner.connect("button-clicked", lambda _banner: self._repair())

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self._editor)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self._banner)
        content.append(scroller)

        self._placeholder = Adw.StatusPage(
            icon_name="application-x-executable-symbolic",
            title="No Application Selected",
            description="Choose an application from the list to edit its launcher.",
        )

        self._stack = Gtk.Stack()
        self._stack.add_named(self._placeholder, "empty")
        self._stack.add_named(content, "app")

        toolbar = Adw.ToolbarView(content=self._stack)
        toolbar.add_top_bar(self._header)
        self.set_child(toolbar)
        self._set_actions_sensitive(False)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()

        maintenance = Gio.Menu()
        maintenance.append("Open Location", "win.open-location")
        maintenance.append("Rebuild Launcher", "win.rebuild-launcher")
        maintenance.append("Replace AppImage…", "win.replace-appimage")
        menu.append_section(None, maintenance)

        presets = Gio.Menu()
        presets.append("Save Settings as Preset…", "win.save-preset")
        menu.append_section(None, presets)

        destructive = Gio.Menu()
        destructive.append("Remove…", "win.remove-app")
        menu.append_section(None, destructive)
        return menu

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @property
    def app(self) -> ManagedApp | None:
        return self._app

    @property
    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def show_app(self, app: ManagedApp | None) -> None:
        """Display ``app``, discarding any unsaved edits to the previous one."""
        self._app = app
        self._dirty = False
        self._save_button.set_sensitive(False)

        if app is None:
            self._stack.set_visible_child_name("empty")
            self.set_title("Application")
            self._banner.set_revealed(False)
            self._set_actions_sensitive(False)
            return

        self.set_title(app.name)
        self._editor.load(app, presets=self._service.presets())
        self._stack.set_visible_child_name("app")
        self._set_actions_sensitive(True)
        self._refresh_banner()

    def _set_actions_sensitive(self, sensitive: bool) -> None:
        self._launch_button.set_sensitive(sensitive)

    def _refresh_banner(self) -> None:
        if self._app is None:
            return
        health = self._service.health(self._app)
        if health is Health.OK:
            self._banner.set_revealed(False)
            self._launch_button.set_sensitive(True)
            return

        self._banner.set_title(self._service.health_message(health))
        if health in (Health.MISSING_LAUNCHER, Health.NOT_EXECUTABLE, Health.MISSING_ICON):
            self._banner.set_button_label("Rebuild Launcher")
        else:
            self._banner.set_button_label("Replace AppImage…")
        self._banner.set_revealed(True)
        self._launch_button.set_sensitive(health is not Health.MISSING_APPIMAGE)

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------
    def _on_editor_changed(self, _editor: AppEditor) -> None:
        self._dirty = True
        self._save_button.set_sensitive(True)

    def save(self) -> bool:
        """Write the edited launcher. Returns ``False`` if the input was bad."""
        if self._app is None:
            return True
        try:
            edited = self._editor.collect()
        except ValueError as error:
            dialogs.present_error(self, "Check the details", str(error))
            return False

        icon_source = self._editor.pending_icon_source
        try:
            updated = self._service.apply_changes(edited, icon_source=icon_source)
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)
            return False

        self._app = updated
        self._dirty = False
        self._save_button.set_sensitive(False)
        self.set_title(updated.name)
        self._editor.load(updated, presets=self._service.presets())
        self._refresh_banner()
        self.emit("app-changed", updated.id)
        return True

    def discard(self) -> None:
        """Throw away unsaved edits and reload from the library."""
        if self._app is not None:
            self.show_app(self._service.get(self._app.id))

    def confirm_discard(self, proceed: Callable[[], None]) -> None:
        """Ask before losing edits, then run ``proceed``."""
        if not self._dirty:
            proceed()
            return

        dialog = Adw.AlertDialog(
            heading="Save changes?",
            body=f"“{self._app.name if self._app else 'This application'}” has "
            "unsaved changes to its launcher.",
        )
        dialog.add_response("cancel", "_Keep Editing")
        dialog.add_response("discard", "_Discard")
        dialog.add_response("save", "_Save")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def responded(_dialog: Adw.AlertDialog, response: str) -> None:
            if response == "save":
                if self.save():
                    proceed()
            elif response == "discard":
                self._dirty = False
                proceed()
            # "cancel" keeps the user in the editor.

        dialog.connect("response", responded)
        dialog.present(self)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _launch(self) -> None:
        if self._app is None:
            return
        try:
            self._service.launch(self._app)
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)
            self._refresh_banner()

    def open_location(self) -> None:
        if self._app is None:
            return
        target = self._app.appimage if self._app.appimage_exists() else self._app.storage_dir
        dialogs.open_in_file_manager(self, target)

    def rebuild_launcher(self) -> None:
        if self._app is None:
            return
        try:
            updated = self._service.rebuild_launcher(self._app)
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)
            return
        self.show_app(updated)
        self.emit("app-changed", updated.id)

    def _repair(self) -> None:
        if self._app is None:
            return
        if self._service.health(self._app) is Health.MISSING_APPIMAGE:
            self.choose_replacement()
        else:
            self.rebuild_launcher()

    def choose_replacement(self) -> None:
        if self._app is None:
            return
        window = self.get_root()
        if not isinstance(window, Gtk.Window):
            return
        app = self._app
        dialogs.open_file(
            window,
            f"Choose a Replacement for {app.name}",
            dialogs.appimage_filters(),
            lambda path: self._start_replacement(app, path),
        )

    def _start_replacement(self, app: ManagedApp, path: Path) -> None:
        replace_appimage(self._service, app, path, self._on_replaced, parent=self)

    def _on_replaced(self, updated: ManagedApp) -> None:
        self.show_app(updated)
        self.emit("app-changed", updated.id)

    def save_as_preset(self) -> None:
        if self._app is None:
            return
        entry = Gtk.Entry(
            placeholder_text="Preset name",
            activates_default=True,
            text=f"{self._app.name} settings",
        )
        dialog = Adw.AlertDialog(
            heading="Save Settings as Preset",
            body="Categories, arguments and launch options are saved. The AppImage "
            "itself is not part of a preset.",
        )
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "_Cancel")
        dialog.add_response("save", "_Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def responded(_dialog: Adw.AlertDialog, response: str) -> None:
            if response != "save" or self._app is None:
                return
            name = entry.get_text().strip()
            if not name:
                return
            try:
                edited = self._editor.collect()
            except ValueError:
                edited = self._app
            self._service.save_preset(Preset.from_app(name, edited))
            self._editor.load(self._app, presets=self._service.presets())

        dialog.connect("response", responded)
        dialog.present(self)

    def remove(self) -> None:
        """Ask what to remove, then do it."""
        if self._app is None:
            return
        app = self._app

        appimage_row = Adw.SwitchRow(
            title="Remove the AppImage",
            subtitle="Deletes the managed copy, not your original download",
            active=True,
        )
        launcher_row = Adw.SwitchRow(
            title="Remove the Launcher",
            subtitle="Takes it out of the applications menu",
            active=True,
        )
        group = Adw.PreferencesGroup()
        group.add(appimage_row)
        group.add(launcher_row)

        def perform() -> None:
            options = RemovalOptions(
                remove_appimage=appimage_row.get_active(),
                remove_launcher=launcher_row.get_active(),
            )
            if not options.remove_appimage and not options.remove_launcher:
                return
            try:
                self._service.remove(app, options)
            except AppimgifyError as error:
                dialogs.present_error(self, error.title, error.detail)
                return
            self._dirty = False
            self.emit("app-removed", app.id)

        if not self._service.settings.confirm_removal:
            perform()
            return

        dialogs.confirm(
            self,
            f"Remove {app.name}?",
            "Your original downloaded AppImage is never touched.",
            confirm_label="_Remove",
            destructive=True,
            extra_child=group,
            on_confirm=perform,
        )
