"""Persistence for launcher presets (``~/.config/appimgify/presets.json``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models.preset import PRESETS_SCHEMA_VERSION, Preset, builtin_presets
from ..utils.fileutils import read_json, write_json
from ..utils.paths import config_dir

PRESETS_FILE_NAME = "presets.json"


class PresetStore:
    """The built-in presets plus whatever the user has saved.

    Built-in presets are never written to disk; only user presets are, so the
    shipped set can change between releases without stale copies lingering.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._path = Path(directory or config_dir()) / PRESETS_FILE_NAME
        self._user: list[Preset] = []
        self._recovered = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def recovered_from_corruption(self) -> bool:
        return self._recovered

    def all(self) -> list[Preset]:
        return [*builtin_presets(), *self._user]

    def user_presets(self) -> list[Preset]:
        return list(self._user)

    def get(self, preset_id: str) -> Preset | None:
        for preset in self.all():
            if preset.id == preset_id:
                return preset
        return None

    def add(self, preset: Preset) -> Preset:
        """Save a preset, replacing any user preset with the same name."""
        self._user = [item for item in self._user if item.name != preset.name]
        self._user.append(preset)
        self.save()
        return preset

    def remove(self, preset_id: str) -> bool:
        remaining = [preset for preset in self._user if preset.id != preset_id]
        if len(remaining) == len(self._user):
            return False
        self._user = remaining
        self.save()
        return True

    def load(self) -> list[Preset]:
        existed = self._path.exists()
        payload = read_json(self._path, default=None)
        self._recovered = existed and payload is None
        self._user = []
        for record in _records_from(payload):
            preset = Preset.from_dict(record)
            if preset is not None:
                self._user.append(preset)
        return self.all()

    def save(self) -> None:
        write_json(
            self._path,
            {
                "schema_version": PRESETS_SCHEMA_VERSION,
                "presets": [preset.to_dict() for preset in self._user],
            },
        )


def _records_from(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        records = payload.get("presets")
        return records if isinstance(records, list) else []
    if isinstance(payload, list):
        return payload
    return []
