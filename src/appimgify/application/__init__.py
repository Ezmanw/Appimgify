"""Application lifecycle."""

from .about import VERSION, present_about
from .application import AppimgifyApplication, main

__all__ = ["AppimgifyApplication", "VERSION", "main", "present_about"]
