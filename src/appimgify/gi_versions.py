"""Pins the GObject Introspection versions the application is written against.

Every package that touches GTK imports this first, so the version requirement
is a property of the library itself rather than of the launcher script. Without
it, importing ``appimgify.ui`` directly — from a test, a distribution's import
check, or a REPL — would let PyGObject bind whichever typelib it happens to
find first and warn about it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
