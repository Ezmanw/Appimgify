"""The import flow: inspect an AppImage, edit its launcher, install it.

Presented as an ``AdwDialog`` on top of the main window.  Nothing is written
outside a temporary directory until the user activates Install, so closing the
dialog at any earlier point is completely free of side effects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from gi.repository import Adw, Gtk

from ..appimages.importer import ImportDraft
from ..models.managed_app import ManagedApp
from ..services import tasks
from ..services.library_service import LibraryService
from ..utils.fileutils import human_size
from . import dialogs
from .editor import AppEditor


class ImportDialog(Adw.Dialog):
    """Guides one AppImage from “selected file” to “installed application”."""

    __gtype_name__ = "AppimgifyImportDialog"

    def __init__(
        self,
        service: LibraryService,
        source: Path,
        *,
        on_finished: Callable[[ManagedApp], None],
    ) -> None:
        super().__init__()
        self._service = service
        self._source = source
        self._on_finished = on_finished
        self._draft: ImportDraft | None = None
        self._task: tasks.BackgroundTask | None = None

        self.set_title("Add AppImage")
        self.set_content_width(660)
        self.set_content_height(720)
        self.connect("closed", self._on_closed)

        self._build()
        self._start_inspection()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._cancel_button = Gtk.Button(label="_Cancel", use_underline=True)
        self._cancel_button.connect("clicked", lambda _button: self.force_close())

        self._install_button = Gtk.Button(label="_Install", use_underline=True)
        self._install_button.add_css_class("suggested-action")
        self._install_button.set_sensitive(False)
        self._install_button.connect("clicked", lambda _button: self._install())

        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        header.pack_start(self._cancel_button)
        header.pack_end(self._install_button)

        self._banner = Adw.Banner(revealed=False)
        self._banner.set_button_label("Details")
        self._banner.connect("button-clicked", lambda _banner: self._show_warnings())

        self._editor = AppEditor(show_storage_details=False)
        editor_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True
        )
        editor_scroller.set_child(self._editor)

        self._spinner_page = Adw.StatusPage(
            title="Inspecting AppImage",
            description=f"Reading application details from “{self._source.name}”",
        )
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        self._spinner_page.set_child(spinner)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._stack.add_named(self._spinner_page, "loading")
        self._stack.add_named(editor_scroller, "editor")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self._banner)
        content.append(self._stack)

        self._progress_bar = Gtk.ProgressBar(show_text=True, text="Copying AppImage…")
        self._progress_revealer = Gtk.Revealer(child=self._wrap_progress())
        self._progress_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)

        toolbar = Adw.ToolbarView(content=content)
        toolbar.add_top_bar(header)
        toolbar.add_bottom_bar(self._progress_revealer)
        self.set_child(toolbar)

    def _wrap_progress(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self._progress_bar)
        return box

    # ------------------------------------------------------------------
    # Phase 1 — inspection
    # ------------------------------------------------------------------
    def _start_inspection(self) -> None:
        source = self._source

        def work(_task: tasks.BackgroundTask) -> ImportDraft:
            return self._service.prepare_import(source)

        self._task = tasks.run(
            work, on_success=self._on_inspected, on_error=self._on_failed
        )

    def _on_inspected(self, draft: ImportDraft) -> None:
        self._task = None
        self._draft = draft
        self._editor.load(
            draft.app, icon_source=draft.icon_source, presets=self._service.presets()
        )
        self._stack.set_visible_child_name("editor")
        self._install_button.set_sensitive(True)
        self._editor.focus_name()
        self._update_banner()

        if draft.duplicate_of is not None:
            self._handle_duplicate(draft.duplicate_of)

    def _update_banner(self) -> None:
        draft = self._draft
        if draft is None or not draft.warnings:
            self._banner.set_revealed(False)
            return
        count = len(draft.warnings)
        self._banner.set_title(
            "Some details could not be read from this AppImage"
            if count > 1
            else draft.warnings[0]
        )
        self._banner.set_revealed(True)

    def _show_warnings(self) -> None:
        if self._draft is None:
            return
        body = "\n\n".join(f"• {warning}" for warning in self._draft.warnings)
        dialogs.present_error(self, "About this AppImage", body)

    # ------------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------------
    def _handle_duplicate(self, existing: ManagedApp) -> None:
        action = self._service.settings.duplicate_action
        if action == "import-anyway":
            return
        if action == "replace":
            self._replace_existing(existing)
            return

        dialogs.choose_response(
            self,
            f"“{existing.name}” is already managed",
            "You can update the existing application to this file, or add this "
            "AppImage as a separate application.",
            (
                ("replace", "_Update Existing", Adw.ResponseAppearance.SUGGESTED),
                ("separate", "Add as _New", Adw.ResponseAppearance.DEFAULT),
                ("cancel", "_Cancel", Adw.ResponseAppearance.DEFAULT),
            ),
            lambda response: self._duplicate_response(response, existing),
        )

    def _duplicate_response(self, response: str, existing: ManagedApp) -> None:
        if response == "replace":
            self._replace_existing(existing)
        elif response == "cancel":
            self.force_close()

    def _replace_existing(self, existing: ManagedApp) -> None:
        """Hand this file over to the replace flow and close the dialog."""
        source = self._source
        self.force_close()
        replace_appimage(self._service, existing, source, self._on_finished)

    # ------------------------------------------------------------------
    # Phase 2 — install
    # ------------------------------------------------------------------
    def _install(self) -> None:
        if self._draft is None:
            return
        try:
            app = self._editor.collect()
        except ValueError as error:
            dialogs.present_error(self, "Check the details", str(error))
            return

        draft = self._draft
        draft.icon_source = self._editor.pending_icon_source or (
            None if self._editor.icon_cleared else draft.icon_source
        )

        self._set_busy(True)
        service = self._service

        def work(task: tasks.BackgroundTask) -> ManagedApp:
            return service.commit_import(
                draft, app, progress=task.report_progress, cancelled=task.token
            )

        self._task = tasks.run(
            work,
            on_success=self._on_installed,
            on_error=self._on_failed,
            on_progress=self._on_progress,
            on_cancelled=lambda: self._set_busy(False),
        )

    def _on_progress(self, current: int, total: int) -> None:
        fraction = (current / total) if total else 0.0
        self._progress_bar.set_fraction(min(1.0, fraction))
        self._progress_bar.set_text(
            f"Copying AppImage — {human_size(current)} of {human_size(total)}"
        )

    def _on_installed(self, app: ManagedApp) -> None:
        self._task = None
        self._draft = None
        self._service.notify_library_changed()
        self._on_finished(app)
        self.force_close()

    def _on_failed(self, error: BaseException) -> None:
        self._task = None
        self._set_busy(False)
        inspection_failed = self._draft is None
        if inspection_failed:
            # Nothing to edit — report against the window and close.
            parent = self.get_parent()
            self.force_close()
            if isinstance(parent, Gtk.Widget):
                dialogs.present_exception(parent, error)
        else:
            dialogs.present_exception(self, error)

    def _set_busy(self, busy: bool) -> None:
        self._install_button.set_sensitive(not busy)
        self._editor.set_sensitive(not busy)
        self._progress_revealer.set_reveal_child(busy)
        self.set_can_close(not busy)
        if busy:
            self._progress_bar.set_fraction(0.0)
            self._progress_bar.set_text("Copying AppImage…")

    # ------------------------------------------------------------------
    def _on_closed(self, _dialog: Adw.Dialog) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._draft is not None:
            self._draft.release()
            self._draft = None


# ----------------------------------------------------------------------
# Replacing an existing application's AppImage
# ----------------------------------------------------------------------
class ReplaceDialog(Adw.AlertDialog):
    """Progress for swapping a managed AppImage for a newer file."""

    __gtype_name__ = "AppimgifyReplaceDialog"

    def __init__(
        self,
        service: LibraryService,
        app: ManagedApp,
        source: Path,
        on_finished: Callable[[ManagedApp], None],
    ) -> None:
        super().__init__(
            heading=f"Updating {app.name}",
            body=f"Copying “{source.name}” into the managed AppImage folder.",
        )
        self._service = service
        self._on_finished = on_finished

        self._progress_bar = Gtk.ProgressBar(show_text=True, text="Copying AppImage…")
        self.set_extra_child(self._progress_bar)
        self.add_response("cancel", "_Cancel")
        self.set_close_response("cancel")
        self.connect("response", self._on_response)

        def work(task: tasks.BackgroundTask) -> ManagedApp:
            return service.replace_appimage(
                app, source, progress=task.report_progress, cancelled=task.token
            )

        self._task = tasks.run(
            work,
            on_success=self._on_success,
            on_error=self._on_error,
            on_progress=self._on_progress,
            on_cancelled=self._on_cancelled,
        )

    def _on_progress(self, current: int, total: int) -> None:
        fraction = (current / total) if total else 0.0
        self._progress_bar.set_fraction(min(1.0, fraction))
        self._progress_bar.set_text(
            f"{human_size(current)} of {human_size(total)}"
        )

    def _on_success(self, app: ManagedApp) -> None:
        self._service.notify_library_changed()
        self._on_finished(app)
        self.close()

    def _on_error(self, error: BaseException) -> None:
        parent = self.get_parent()
        self.close()
        if isinstance(parent, Gtk.Widget):
            dialogs.present_exception(parent, error)

    def _on_cancelled(self) -> None:
        self.close()

    def _on_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "cancel" and self._task is not None:
            self._task.cancel()


def replace_appimage(
    service: LibraryService,
    app: ManagedApp,
    source: Path,
    on_finished: Callable[[ManagedApp], None],
    parent: Gtk.Widget | None = None,
) -> None:
    """Validate and swap in a replacement AppImage, showing progress."""
    host = parent or _active_window()
    if host is None:
        return
    ReplaceDialog(service, app, source, on_finished).present(host)


def _active_window() -> Gtk.Window | None:
    application = Gtk.Application.get_default()
    return application.get_active_window() if application is not None else None
