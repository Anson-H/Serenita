from __future__ import annotations

import threading
from collections.abc import Callable


class OperationCancelledError(RuntimeError):
    """Raised when an in-flight operation has been explicitly cancelled."""


class CancellationToken:
    """Thread-safe cancellation signal with hooks for closing blocking I/O."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: dict[object, Callable[[], None]] = {}

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise OperationCancelledError("操作已取消。")

    def register(self, callback: Callable[[], None]) -> Callable[[], None]:
        callback_id = object()
        invoke_now = False
        with self._lock:
            if self._cancelled.is_set():
                invoke_now = True
            else:
                self._callbacks[callback_id] = callback

        if invoke_now:
            self._invoke(callback)

        def unregister() -> None:
            with self._lock:
                self._callbacks.pop(callback_id, None)

        return unregister

    def cancel(self) -> None:
        with self._lock:
            if self._cancelled.is_set():
                return
            self._cancelled.set()
            callbacks = list(reversed(self._callbacks.values()))
            self._callbacks.clear()
        for callback in callbacks:
            self._invoke(callback)

    @staticmethod
    def _invoke(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            # Cancellation must remain best-effort across multiple resources;
            # one already-closed handle cannot prevent the others from closing.
            pass
