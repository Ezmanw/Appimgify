"""The library file — the authoritative record of managed applications.

Stored at ``~/.local/share/appimgify/library.json``.  Because this file, not
the generated ``.desktop`` entries, is the source of truth, a launcher that a
user deleted or a desktop environment mangled can always be regenerated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ..models.managed_app import LIBRARY_SCHEMA_VERSION, ManagedApp
from ..utils.fileutils import read_json, write_json
from ..utils.paths import data_dir

LIBRARY_FILE_NAME = "library.json"


class Library:
    """An ordered collection of :class:`ManagedApp` records with persistence."""

    def __init__(self, directory: Path | None = None) -> None:
        self._path = Path(directory or data_dir()) / LIBRARY_FILE_NAME
        self._apps: list[ManagedApp] = []
        self._recovered = False
        self._skipped = 0

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    @property
    def recovered_from_corruption(self) -> bool:
        return self._recovered

    @property
    def skipped_records(self) -> int:
        """Records that could not be understood and were dropped on load."""
        return self._skipped

    def __iter__(self) -> Iterator[ManagedApp]:
        return iter(self._apps)

    def __len__(self) -> int:
        return len(self._apps)

    @property
    def apps(self) -> list[ManagedApp]:
        return list(self._apps)

    def get(self, app_id: str) -> ManagedApp | None:
        for app in self._apps:
            if app.id == app_id:
                return app
        return None

    def ids(self) -> set[str]:
        return {app.id for app in self._apps}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def add(self, app: ManagedApp) -> ManagedApp:
        self._apps.append(app)
        self.save()
        return app

    def update(self, app: ManagedApp) -> ManagedApp:
        """Replace the record with the same id, appending it if it is new."""
        for index, existing in enumerate(self._apps):
            if existing.id == app.id:
                self._apps[index] = app
                break
        else:
            self._apps.append(app)
        self.save()
        return app

    def remove(self, app_id: str) -> ManagedApp | None:
        for index, existing in enumerate(self._apps):
            if existing.id == app_id:
                removed = self._apps.pop(index)
                self.save()
                return removed
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load(self) -> list[ManagedApp]:
        """Read the library, skipping records that cannot be understood."""
        existed = self._path.exists()
        payload = read_json(self._path, default=None)
        self._recovered = existed and payload is None
        self._skipped = 0
        self._apps = []

        records = _records_from(payload)
        for record in records:
            app = ManagedApp.from_dict(record)
            if app is None:
                self._skipped += 1
                continue
            self._apps.append(app)
        self._deduplicate()
        return self.apps

    def save(self) -> None:
        write_json(
            self._path,
            {
                "schema_version": LIBRARY_SCHEMA_VERSION,
                "applications": [app.to_dict() for app in self._apps],
            },
        )

    def _deduplicate(self) -> None:
        """Guard against a hand-edited file containing repeated ids."""
        seen: set[str] = set()
        unique: list[ManagedApp] = []
        for app in self._apps:
            if app.id in seen:
                self._skipped += 1
                continue
            seen.add(app.id)
            unique.append(app)
        self._apps = unique


def _records_from(payload: Any) -> list[Any]:
    """Accept both the current object form and a bare list of applications."""
    if isinstance(payload, dict):
        records = payload.get("applications")
        return records if isinstance(records, list) else []
    if isinstance(payload, list):
        return payload
    return []
