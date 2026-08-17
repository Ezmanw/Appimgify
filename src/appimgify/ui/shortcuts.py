"""The standard GTK keyboard shortcuts window."""

from __future__ import annotations

from gi.repository import Gtk

_SHORTCUTS = (
    ("General", (
        ("<Control>n", "Add an AppImage"),
        ("<Control>f", "Search applications"),
        ("<Control>comma", "Preferences"),
        ("<Control>question", "Keyboard shortcuts"),
        ("<Control>w", "Close window"),
        ("<Control>q", "Quit"),
    )),
    ("Applications", (
        ("<Control>Return", "Launch the selected application"),
        ("<Control>s", "Save launcher changes"),
        ("Delete", "Remove the selected application"),
    )),
)


def shortcuts_window(parent: Gtk.Window) -> Gtk.ShortcutsWindow:
    """Build the shortcuts window from the standard GTK widgets."""
    section = Gtk.ShortcutsSection(section_name="shortcuts", max_height=10, visible=True)
    for title, entries in _SHORTCUTS:
        group = Gtk.ShortcutsGroup(title=title, visible=True)
        for accelerator, description in entries:
            group.add_shortcut(
                Gtk.ShortcutsShortcut(
                    accelerator=accelerator, title=description, visible=True
                )
            )
        section.add_group(group)

    window = Gtk.ShortcutsWindow(modal=True, transient_for=parent)
    window.add_section(section)
    return window
