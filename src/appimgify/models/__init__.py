"""Plain data types shared by every other layer.

Nothing in this package imports GTK, so the model can be exercised from tests
and from worker threads.
"""

from .categories import MAIN_CATEGORIES, describe, is_main_category, label_for, normalise
from .managed_app import LIBRARY_SCHEMA_VERSION, ManagedApp
from .metadata import ExtractedMetadata
from .preset import PRESETS_SCHEMA_VERSION, Preset, builtin_presets

__all__ = [
    "MAIN_CATEGORIES",
    "LIBRARY_SCHEMA_VERSION",
    "PRESETS_SCHEMA_VERSION",
    "ExtractedMetadata",
    "ManagedApp",
    "Preset",
    "builtin_presets",
    "describe",
    "is_main_category",
    "label_for",
    "normalise",
]
