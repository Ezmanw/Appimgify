"""The main window: an ``AdwNavigationSplitView`` over the application library.

The sidebar lists managed applications with search, category filtering and
sorting; the content pane holds the launcher editor for whichever one is
selected.  AppImages can also be dropped straight onto the window.
"""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from ..models import categories as categories_module
from ..models.managed_app import ManagedApp
from ..services.library_service import LibraryService
from ..utils.errors import AppimgifyError
from . import dialogs
from .app_row import AppRow
from .detail import AppDetailPage
from .import_dialog import ImportDialog
from .preferences import PreferencesWindow

SORT_ORDERS = (("name", "Name"), ("recent", "Recently Added"), ("category", "Category"))


class MainWindow(Adw.ApplicationWindow):
    """The application's only window."""

    __gtype_name__ = "AppimgifyMainWindow"

    def __init__(self, application: Adw.Application, service: LibraryService) -> None:
        super().__init__(application=application)
        self._service = service
        self._rows: dict[str, AppRow] = {}
        self._selected_id: str | None = None
        self._search_text = ""
        self._category_filter = ""

        settings = service.settings
        self.set_title("Appimgify")
        # The smallest size the layout stays usable at, as required by the
        # adaptive breakpoint below.
        self.set_size_request(360, 294)
        self.set_default_size(settings.window_width, settings.window_height)
        if settings.window_maximized:
            self.maximize()

        self._build()
        self._register_actions()
        self._connect_service()
        self._setup_drop_target()
        self.refresh()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._detail = AppDetailPage(self._service)
        self._detail.connect("app-changed", lambda _page, app_id: self.refresh(app_id))
        self._detail.connect("app-removed", self._on_app_removed)

        self._split_view = Adw.NavigationSplitView(
            sidebar=self._build_sidebar(),
            content=self._detail,
            min_sidebar_width=280,
            max_sidebar_width=380,
        )

        self._toasts = Adw.ToastOverlay(child=self._split_view)

        self._drop_hint = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            can_target=False,
            child=Adw.StatusPage(
                icon_name="folder-download-symbolic",
                title="Drop to Add",
                description="Release to import this AppImage",
            ),
        )
        self._drop_hint.get_child().add_css_class("background")

        overlay = Gtk.Overlay(child=self._toasts)
        overlay.add_overlay(self._drop_hint)

        breakpoint_ = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 640sp")
        )
        breakpoint_.add_setter(self._split_view, "collapsed", True)
        self.add_breakpoint(breakpoint_)

        self.set_content(overlay)

    def _build_sidebar(self) -> Adw.NavigationPage:
        add_button = Gtk.Button(
            child=Adw.ButtonContent(icon_name="list-add-symbolic", label="Add"),
            tooltip_text="Import an AppImage (Ctrl+N)",
            action_name="win.add-appimage",
        )

        self._search_button = Gtk.ToggleButton(
            icon_name="system-search-symbolic", tooltip_text="Search applications (Ctrl+F)"
        )

        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Main menu",
            primary=True,
            menu_model=self._build_primary_menu(),
        )

        header = Adw.HeaderBar()
        header.pack_start(add_button)
        header.pack_end(menu_button)
        header.pack_end(self._search_button)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Search applications")
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_bar = Gtk.SearchBar(
            child=self._search_entry, show_close_button=False, key_capture_widget=self
        )
        self._search_bar.connect_entry(self._search_entry)
        self._search_button.bind_property(
            "active",
            self._search_bar,
            "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        self._filter_bar = self._build_filter_bar()

        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.connect("row-activated", self._on_row_activated)
        self._list_box.set_accessible_role(Gtk.AccessibleRole.LIST)
        self._list_box.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Managed applications"]
        )

        list_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=self._list_box
        )

        self._empty_page = Adw.StatusPage(
            icon_name="application-x-executable-symbolic",
            title="No AppImages Yet",
            description="Import an AppImage to give it a proper launcher in your "
            "applications menu. You can also drop one onto this window.",
        )
        empty_button = Gtk.Button(
            label="_Add AppImage…",
            use_underline=True,
            halign=Gtk.Align.CENTER,
            action_name="win.add-appimage",
        )
        empty_button.add_css_class("suggested-action")
        empty_button.add_css_class("pill")
        self._empty_page.set_child(empty_button)

        self._no_results_page = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title="No Results Found",
            description="Try a different search term or category.",
        )

        self._list_stack = Gtk.Stack()
        self._list_stack.add_named(list_scroller, "list")
        self._list_stack.add_named(self._empty_page, "empty")
        self._list_stack.add_named(self._no_results_page, "no-results")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self._search_bar)
        content.append(self._filter_bar)
        content.append(self._list_stack)

        toolbar = Adw.ToolbarView(content=content)
        toolbar.add_top_bar(header)
        return Adw.NavigationPage(title="Applications", child=toolbar)

    def _build_filter_bar(self) -> Gtk.Widget:
        self._category_model = Gtk.StringList.new(["All Categories"])
        self._category_dropdown = Gtk.DropDown(
            model=self._category_model, tooltip_text="Filter by category", hexpand=True
        )
        self._category_dropdown.connect("notify::selected", self._on_category_changed)
        self._category_dropdown.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Filter by category"]
        )

        self._sort_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new([label for _value, label in SORT_ORDERS]),
            tooltip_text="Sort applications",
            hexpand=True,
        )
        self._sort_dropdown.set_selected(
            next(
                (
                    index
                    for index, (value, _label) in enumerate(SORT_ORDERS)
                    if value == self._service.settings.sort_order
                ),
                0,
            )
        )
        self._sort_dropdown.connect("notify::selected", self._on_sort_changed)
        self._sort_dropdown.update_property(
            [Gtk.AccessibleProperty.LABEL], ["Sort applications"]
        )

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self._category_dropdown)
        box.append(self._sort_dropdown)
        return box

    def _build_primary_menu(self) -> Gio.Menu:
        menu = Gio.Menu()

        library = Gio.Menu()
        library.append("Add AppImage…", "win.add-appimage")
        library.append("Open AppImage Folder", "win.open-storage")
        library.append("Check for Problems", "win.check-problems")
        menu.append_section(None, library)

        application = Gio.Menu()
        application.append("Preferences", "win.preferences")
        application.append("Keyboard Shortcuts", "win.shortcuts")
        application.append("About Appimgify", "win.about")
        menu.append_section(None, application)

        quit_section = Gio.Menu()
        quit_section.append("Quit", "app.quit")
        menu.append_section(None, quit_section)
        return menu

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _register_actions(self) -> None:
        definitions = {
            "add-appimage": self.add_appimage,
            "open-storage": self._open_storage,
            "check-problems": self._check_problems,
            "preferences": self._open_preferences,
            "shortcuts": self._show_shortcuts,
            "about": self._show_about,
            "search": self._focus_search,
            "open-location": self._detail.open_location,
            "rebuild-launcher": self._detail.rebuild_launcher,
            "replace-appimage": self._detail.choose_replacement,
            "save-preset": self._detail.save_as_preset,
            "remove-app": self._detail.remove,
        }
        for name, callback in definitions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, cb=callback: cb())
            self.add_action(action)

    def _focus_search(self) -> None:
        self._search_button.set_active(True)
        self._search_entry.grab_focus()

    # ------------------------------------------------------------------
    # Service wiring
    # ------------------------------------------------------------------
    def _connect_service(self) -> None:
        self._service.connect("library-changed", lambda _service: self.refresh())
        self._service.connect("notice", lambda _service, text: self.toast(text))
        self._service.connect("settings-changed", lambda _service: self.refresh())

    def toast(self, text: str) -> None:
        self._toasts.add_toast(Adw.Toast.new(text))

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------
    def refresh(self, select_id: str | None = None) -> None:
        """Rebuild the sidebar list from the service and restore selection."""
        target_id = select_id or self._selected_id
        self._refresh_category_filter()

        apps = self._service.filtered(self._search_text, self._category_filter)
        self._list_box.remove_all()
        self._rows.clear()

        for app in apps:
            health = self._service.health(app)
            row = AppRow(app, health, self._service.health_message(health))
            self._list_box.append(row)
            self._rows[app.id] = row

        if not len(self._service.apps):
            self._list_stack.set_visible_child_name("empty")
        elif not apps:
            self._list_stack.set_visible_child_name("no-results")
        else:
            self._list_stack.set_visible_child_name("list")

        self._restore_selection(target_id, apps)

    def _restore_selection(self, target_id: str | None, apps: list[ManagedApp]) -> None:
        row = self._rows.get(target_id) if target_id else None
        if row is None and apps and not self._split_view.get_collapsed():
            row = self._rows.get(apps[0].id)
        if row is None:
            self._selected_id = None
            self._list_box.unselect_all()
            self._detail.show_app(None)
            return
        self._list_box.select_row(row)
        self._selected_id = row.app_id
        self._detail.show_app(self._service.get(row.app_id))

    def _refresh_category_filter(self) -> None:
        used = self._service.used_categories()
        labels = ["All Categories", *(categories_module.label_for(v) for v in used)]
        self._category_values = ["", *used]
        current = self._category_filter

        self._category_dropdown.handler_block_by_func(self._on_category_changed)
        self._category_model.splice(0, self._category_model.get_n_items(), labels)
        index = self._category_values.index(current) if current in self._category_values else 0
        self._category_dropdown.set_selected(index)
        self._category_filter = self._category_values[index]
        self._category_dropdown.handler_unblock_by_func(self._on_category_changed)

    # ------------------------------------------------------------------
    # List interaction
    # ------------------------------------------------------------------
    def _on_row_activated(self, _list_box: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if not isinstance(row, AppRow):
            return
        if row.app_id == self._selected_id:
            if self._split_view.get_collapsed():
                self._split_view.set_show_content(True)
            return

        target_id = row.app_id

        def proceed() -> None:
            self._selected_id = target_id
            selected = self._rows.get(target_id)
            if selected is not None:
                self._list_box.select_row(selected)
            self._detail.show_app(self._service.get(target_id))
            if self._split_view.get_collapsed():
                self._split_view.set_show_content(True)

        if self._detail.has_unsaved_changes:
            # Keep the selection on the application being edited until the
            # user has decided what to do with their changes.
            previous = self._rows.get(self._selected_id or "")
            if previous is not None:
                self._list_box.select_row(previous)
            self._detail.confirm_discard(proceed)
        else:
            proceed()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_text = entry.get_text()
        self.refresh()

    def _on_category_changed(self, *_args: object) -> None:
        index = self._category_dropdown.get_selected()
        values = getattr(self, "_category_values", [""])
        self._category_filter = values[index] if 0 <= index < len(values) else ""
        self.refresh()

    def _on_sort_changed(self, *_args: object) -> None:
        index = self._sort_dropdown.get_selected()
        if 0 <= index < len(SORT_ORDERS):
            settings = self._service.settings
            settings.sort_order = SORT_ORDERS[index][0]
            self._service.update_settings(settings)

    def _on_app_removed(self, _page: AppDetailPage, app_id: str) -> None:
        self.toast("Application removed")
        if self._selected_id == app_id:
            self._selected_id = None
        self.refresh()

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def add_appimage(self) -> None:
        dialogs.open_file(
            self,
            "Choose an AppImage",
            dialogs.appimage_filters(),
            self.import_path,
            initial_folder=_downloads_folder(),
        )

    def import_path(self, path: Path) -> None:
        """Start the import flow for a file chosen or dropped by the user."""
        dialog = ImportDialog(self._service, path, on_finished=self._on_imported)
        dialog.present(self)

    def _on_imported(self, app: ManagedApp) -> None:
        self.refresh(app.id)
        toast = Adw.Toast.new(f"“{app.name}” was added to your applications")
        if self._service.settings.launch_after_import:
            try:
                self._service.launch(app)
            except AppimgifyError as error:
                dialogs.present_error(self, error.title, error.detail)
        else:
            toast.set_button_label("Launch")
            toast.connect("button-clicked", lambda _toast: self._launch_by_id(app.id))
        self._toasts.add_toast(toast)

    def _launch_by_id(self, app_id: str) -> None:
        app = self._service.get(app_id)
        if app is None:
            return
        try:
            self._service.launch(app)
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------
    def _setup_drop_target(self) -> None:
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("enter", self._on_drag_enter)
        target.connect("leave", self._on_drag_leave)
        target.connect("drop", self._on_drop)
        self.add_controller(target)

    def _on_drag_enter(self, _target: Gtk.DropTarget, _x: float, _y: float) -> Gdk.DragAction:
        self._drop_hint.set_reveal_child(True)
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, _target: Gtk.DropTarget) -> None:
        self._drop_hint.set_reveal_child(False)

    def _on_drop(
        self, _target: Gtk.DropTarget, value: Gdk.FileList, _x: float, _y: float
    ) -> bool:
        self._drop_hint.set_reveal_child(False)
        files = [file.get_path() for file in value.get_files() if file.get_path()]
        if not files:
            return False
        if len(files) > 1:
            self.toast("Drop one AppImage at a time")
        self.import_path(Path(files[0]))
        return True

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def _open_storage(self) -> None:
        try:
            self._service.store.ensure_ready()
        except AppimgifyError as error:
            dialogs.present_error(self, error.title, error.detail)
            return
        dialogs.open_in_file_manager(self, self._service.store.root)

    def _check_problems(self) -> None:
        problems = self._service.problems()
        orphans = self._service.orphaned_launchers()
        if not problems and not orphans:
            self.toast("Everything looks fine")
            return

        lines = [
            f"• {app.name}: {self._service.health_message(health)}"
            for app, health in problems
        ]
        if orphans:
            lines.append(
                f"• {len(orphans)} leftover launcher"
                f"{'' if len(orphans) == 1 else 's'} without a matching application"
            )

        def clean_up() -> None:
            removed = self._service.forget_orphans()
            if removed:
                self.toast(f"Removed {removed} leftover launcher{'' if removed == 1 else 's'}")

        if orphans:
            dialogs.confirm(
                self,
                "Some Things Need Attention",
                "\n".join(lines),
                confirm_label="_Remove Leftovers",
                on_confirm=clean_up,
                destructive=True,
            )
        else:
            dialogs.present_error(self, "Some Things Need Attention", "\n".join(lines))

    def _open_preferences(self) -> None:
        window = PreferencesWindow(self._service)
        window.set_transient_for(self)
        window.set_modal(True)
        window.present()

    def _show_shortcuts(self) -> None:
        from .shortcuts import shortcuts_window

        shortcuts_window(self).present()

    def _show_about(self) -> None:
        from ..application.about import present_about

        present_about(self)

    # ------------------------------------------------------------------
    def save_state(self) -> None:
        """Persist window geometry on close."""
        width, height = self.get_default_size()
        self._service.save_window_state(width, height, self.is_maximized())


def _downloads_folder() -> Path | None:
    directory = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    return Path(directory) if directory else None
