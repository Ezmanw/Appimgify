"""Filesystem primitives shared by the storage and persistence layers.

These helpers are deliberately free of any GTK dependency so they can be unit
tested and reused from worker threads.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

from .errors import PersistenceError

#: Called as ``progress(copied_bytes, total_bytes)`` during long copies.
ProgressCallback = Callable[[int, int], None]
#: Returns ``True`` when the running operation should abort.
CancelCallback = Callable[[], bool]

_COPY_CHUNK = 1024 * 1024


def make_executable(path: Path) -> None:
    """Add the execute bit for every role that can already read the file."""
    mode = path.stat().st_mode
    extra = (mode & 0o444) >> 2  # r -> x for user/group/other
    path.chmod(stat.S_IMODE(mode | extra | stat.S_IXUSR))


def is_executable(path: Path) -> bool:
    return os.access(str(path), os.X_OK)


def copy_file(
    source: Path,
    destination: Path,
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> None:
    """Copy ``source`` to ``destination`` atomically.

    The data is streamed into a sibling temporary file and only moved into
    place once it is complete and flushed, so an interrupted or cancelled copy
    can never leave a half-written AppImage behind.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = source.stat().st_size
    copied = 0
    handle, temp_name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=f".{destination.name}.", suffix=".part"
    )
    temp_path = Path(temp_name)
    try:
        with open(handle, "wb") as target, open(source, "rb") as origin:
            while True:
                if cancelled is not None and cancelled():
                    raise InterruptedError("copy cancelled")
                chunk = origin.read(_COPY_CHUNK)
                if not chunk:
                    break
                target.write(chunk)
                copied += len(chunk)
                if progress is not None:
                    progress(copied, total)
            target.flush()
            os.fsync(target.fileno())
        shutil.copystat(source, temp_path, follow_symlinks=True)
        os.replace(temp_path, destination)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    if progress is not None:
        progress(total, total)


def write_text_atomic(path: Path, contents: str) -> None:
    """Write ``contents`` to ``path`` via a temporary file and ``os.replace``.

    Readers therefore only ever observe the previous file or the complete new
    one, never a truncated launcher.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    temp_path = Path(temp_name)
    try:
        with open(handle, "w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def write_json(path: Path, payload: Any) -> None:
    """Serialise ``payload`` to ``path`` atomically and readably."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    temp_path = Path(temp_name)
    try:
        with open(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except OSError as error:
        temp_path.unlink(missing_ok=True)
        raise PersistenceError(
            "Could not save data", f"Writing “{path}” failed: {error.strerror or error}."
        ) from error
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON from ``path``, returning ``default`` for anything unusable.

    A missing file is normal.  A corrupted file is not fatal either: it is
    moved aside as ``<name>.corrupt`` so the user keeps their data and the
    application starts with clean state instead of refusing to run.
    """
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (json.JSONDecodeError, UnicodeDecodeError):
        quarantine_corrupt(path)
        return default
    except OSError:
        return default


def quarantine_corrupt(path: Path) -> Path | None:
    """Move an unreadable file aside so a fresh one can be written."""
    backup = path.with_suffix(path.suffix + ".corrupt")
    counter = 2
    while backup.exists():
        backup = path.with_suffix(f"{path.suffix}.corrupt-{counter}")
        counter += 1
    try:
        os.replace(path, backup)
        return backup
    except OSError:
        return None


def remove_tree(path: Path) -> None:
    """Delete a file, symlink or directory, ignoring what is already gone."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def prune_empty_dirs(path: Path, stop_at: Path) -> None:
    """Remove ``path`` and empty parents, never climbing past ``stop_at``."""
    current = path
    while current != stop_at and stop_at in current.parents:
        try:
            next(current.iterdir())
            return
        except StopIteration:
            try:
                current.rmdir()
            except OSError:
                return
        except (OSError, ValueError):
            return
        current = current.parent


def human_size(num_bytes: int) -> str:
    """Format a byte count the way GNOME does (decimal units)."""
    units: Iterable[str] = ("kB", "MB", "GB", "TB")
    if num_bytes < 1000:
        return f"{num_bytes} bytes"
    value = float(num_bytes)
    unit = "kB"
    for unit in units:
        value /= 1000.0
        if value < 1000.0:
            break
    return f"{value:.1f} {unit}"
