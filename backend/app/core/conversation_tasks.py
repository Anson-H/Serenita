"""Shared in-process execution state for one data root."""

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from backend.app.core.cancellation import CancellationToken
from backend.app.session_event_notifications import SessionEventNotifications


@dataclass
class ConversationTasks:
    lock: object = field(default_factory=threading.Lock)
    session_locks: dict = field(default_factory=dict)
    threads: dict = field(default_factory=dict)
    cancellations: dict[tuple[str, str, str], CancellationToken] = field(
        default_factory=dict
    )
    titles: dict = field(default_factory=dict)
    notifications: SessionEventNotifications = field(
        default_factory=SessionEventNotifications
    )

    def session_lock(self, account_id: str, session_id: str):
        with self.lock:
            return self.session_locks.setdefault(
                (account_id, session_id), threading.RLock()
            )

    def wait(self, timeout=2.0):
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                threads = [
                    *self.threads.values(),
                    *(thread for thread, _ in self.titles.values()),
                ]
            if not threads or time.monotonic() >= deadline:
                return
            for thread in threads:
                if thread is not threading.current_thread():
                    thread.join(timeout=max(0, min(deadline - time.monotonic(), 0.1)))


_registry_lock = threading.Lock()
_tasks: dict[Path, ConversationTasks] = {}


def tasks_for_paths(paths) -> ConversationTasks:
    with _registry_lock:
        return _tasks.setdefault(paths.root.resolve(), ConversationTasks())


def wait_for_all_jobs(timeout=2.0):
    deadline = time.monotonic() + timeout
    with _registry_lock:
        states = list(_tasks.values())
    for state in states:
        state.wait(max(0, deadline - time.monotonic()))
