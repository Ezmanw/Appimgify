"""The list row used for one managed application in the library sidebar."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ..models.managed_app import ManagedApp
from ..services.library_service import Health
from . import iconview

LIST_ICON_SIZE = 32

#: System theme icons indicating an application's state.
_HEALTH_ICONS = {
    Health.MISSING_APPIMAGE: "dialog-warning-symbolic",
    Health.NOT_EXECUTABLE: "dialog-warning-symbolic",
    Health.MISSING_LAUNCHER: "dialog-information-symbolic",
    Health.MISSING_ICON: "dialog-information-symbolic",
}


class AppRow(Adw.ActionRow):
    """An ``AdwActionRow`` showing an application's icon, name and state."""

    __gtype_name__ = "AppimgifyAppRow"

    def __init__(self, app: ManagedApp, health: Health, health_message: str) -> None:
        super().__init__(activatable=True)
        self.app_id = app.id

        self._icon = iconview.icon_image(app.icon, LIST_ICON_SIZE)
        self.add_prefix(self._icon)

        self._status = Gtk.Image(valign=Gtk.Align.CENTER)
        self._status.set_pixel_size(16)
        self.add_suffix(self._status)

        self.update(app, health, health_message)

    def update(self, app: ManagedApp, health: Health, health_message: str) -> None:
        self.app_id = app.id
        self.set_title(escape_markup(app.name))
        self.set_subtitle(escape_markup(app.display_subtitle()))
        iconview.apply_icon(self._icon, app.icon)

        icon_name = _HEALTH_ICONS.get(health)
        if icon_name is None:
            self._status.set_visible(False)
            self.set_tooltip_text(None)
            self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [app.display_subtitle()])
        else:
            self._status.set_from_icon_name(icon_name)
            self._status.set_visible(True)
            self._status.set_tooltip_text(health_message)
            self.set_tooltip_text(health_message)
            self.update_property(
                [Gtk.AccessibleProperty.DESCRIPTION],
                [f"{app.display_subtitle()}. {health_message}"],
            )


def escape_markup(text: str) -> str:
    """Escape markup so an application name containing ``&`` renders correctly.

    ``AdwActionRow`` titles use Pango markup, and AppImage authors do put
    ampersands in application names.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
