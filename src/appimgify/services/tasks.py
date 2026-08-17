"""Running slow work off the main loop.

Copying a 300 MB AppImage or unpacking a payload must never block the UI, so
those operations run on a worker thread and report back through
``GLib.idle_add``, which is the only safe way to touch GTK from another thread.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from gi.repository import GLib


class CancellationToken:
    """A thread-safe “please stop” flag shared with a running operation."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def __call__(self) -> bool:
        return self._event.is_set()


class BackgroundTask:
    """One unit of background work with main-loop callbacks.

    ``on_progress``, ``on_success`` and ``on_error`` are always invoked on the
    main loop, so callers can update widgets directly from them.
    """

    def __init__(
        self,
        work: Callable[["BackgroundTask"], Any],
        *,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        self._work = work
        self._on_success = on_success
        self._on_error = on_error
        self._on_progress = on_progress
        self._on_cancelled = on_cancelled
        self.token = CancellationToken()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def start(self) -> "BackgroundTask":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def cancel(self) -> None:
        self.token.cancel()

    @property
    def cancelled(self) -> bool:
        return self.token.cancelled

    def report_progress(self, current: int, total: int) -> None:
        """Callable passed into worker code as its progress callback."""
        if self._on_progress is not None:
            GLib.idle_add(self._on_progress, current, total, priority=GLib.PRIORITY_DEFAULT)

    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            result = self._work(self)
        except InterruptedError:
            self._dispatch_cancelled()
        except BaseException as error:  # reported to the user, never printed away
            if self.token.cancelled:
                self._dispatch_cancelled()
            else:
                traceback.print_exc()
                self._dispatch(self._on_error, error)
        else:
            if self.token.cancelled:
                self._dispatch_cancelled()
            else:
                self._dispatch(self._on_success, result)

    def _dispatch_cancelled(self) -> None:
        if self._on_cancelled is not None:
            GLib.idle_add(self._on_cancelled)

    @staticmethod
    def _dispatch(callback: Callable[[Any], None] | None, value: Any) -> None:
        if callback is not None:
            GLib.idle_add(callback, value)


def run(
    work: Callable[[BackgroundTask], Any],
    *,
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_cancelled: Callable[[], None] | None = None,
) -> BackgroundTask:
    """Convenience wrapper: build a :class:`BackgroundTask` and start it."""
    task = BackgroundTask(
        work,
        on_success=on_success,
        on_error=on_error,
        on_progress=on_progress,
        on_cancelled=on_cancelled,
    )
    return task.start()
