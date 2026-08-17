"""Launcher generation and installation."""

from .entry import build_exec, desktop_file_name, escape_value, quote_exec_argument, render
from .installer import DesktopEntryInstaller, LauncherBackend, launch

__all__ = [
    "DesktopEntryInstaller",
    "LauncherBackend",
    "build_exec",
    "desktop_file_name",
    "escape_value",
    "launch",
    "quote_exec_argument",
    "render",
]
