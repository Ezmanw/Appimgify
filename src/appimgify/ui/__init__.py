"""The user interface — GTK 4 and Libadwaita widgets only."""

from .. import gi_versions  # noqa: F401  (pins typelib versions before Gtk)
from .window import MainWindow

__all__ = ["MainWindow"]
