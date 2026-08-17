"""Application lifecycle."""

from .. import gi_versions  # noqa: F401  (pins typelib versions before Adw)
from .about import VERSION, present_about
from .application import AppimgifyApplication, main

__all__ = ["AppimgifyApplication", "VERSION", "main", "present_about"]
