"""The standard About window.

The application icon is the one installed into the system icon theme by the
build; nothing is drawn here.
"""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ..metadata.extractor import extraction_method_available
from ..utils.paths import (
    APP_ID,
    config_dir,
    contract_user,
    data_dir,
    default_appimage_dir,
    default_launcher_dir,
)

VERSION = "1.0.0"


def present_about(parent: Gtk.Window) -> None:
    about = Adw.AboutWindow(
        transient_for=parent,
        application_name="Appimgify",
        application_icon=APP_ID,
        version=VERSION,
        developer_name="The Appimgify Contributors",
        comments=(
            "Import AppImages into a managed folder and give them proper "
            "launchers in your applications menu."
        ),
        website="https://github.com/Ezmanw/Appimgify",
        issue_url="https://github.com/Ezmanw/Appimgify/issues",
        license_type=Gtk.License.GPL_3_0,
    )
    about.add_credit_section("Built With", ["GTK 4", "Libadwaita", "PyGObject"])
    about.set_debug_info(_debug_info())
    about.set_debug_info_filename("appimgify-debug.txt")
    about.present()


def _debug_info() -> str:
    """Paths and capabilities, so bug reports contain what matters."""
    lines = [
        f"Appimgify {VERSION}",
        f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
        f"Libadwaita {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}.{Adw.MICRO_VERSION}",
        "",
        f"AppImage folder:   {contract_user(default_appimage_dir())}",
        f"Launcher folder:   {contract_user(default_launcher_dir())}",
        f"Configuration:     {contract_user(config_dir())}",
        f"Library data:      {contract_user(data_dir())}",
        f"Metadata backend:  {extraction_method_available()}",
    ]
    return "\n".join(lines)
