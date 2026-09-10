"""Thread-safe, data-root-scoped wakeups. Durable state stays in repositories."""

import threading
from uuid import uuid4
from collections import defaultdict


class NotificationRuntime:
    def __init__(self):
        self.condition = threading.Condition()
        self.epoch = str(uuid4())
        self.revisions = defaultdict(int)
        self.generation = 0
        self.schedule_generation = 0
        self.listeners = defaultdict(set)

    def changed(self, accounts=(), *, reschedule=False):
        with self.condition:
            for account in accounts:
                self.revisions[account] += 1
                for loop, queue in tuple(self.listeners[account]):

                    def offer(q=queue):
                        if q.empty():
                            q.put_nowait(True)

                    if not loop.is_closed():
                        loop.call_soon_threadsafe(offer)
            self.generation += 1
            if reschedule:
                self.schedule_generation += 1
            self.condition.notify_all()

    def revision(self, account):
        with self.condition:
            return f"{self.epoch}:{self.revisions[account]}"

    def wait(self, generation, timeout):
        with self.condition:
            self.condition.wait_for(
                lambda: generation != self.generation, timeout=timeout
            )

    def subscribe(self, account, listener):
        with self.condition:
            self.listeners[account].add(listener)

    def unsubscribe(self, account, listener):
        with self.condition:
            self.listeners[account].discard(listener)
            if not self.listeners[account]:
                self.listeners.pop(account, None)


_lock = threading.Lock()
_runtimes = {}


def notification_runtime(paths):
    key = str(paths.root.resolve())
    with _lock:
        return _runtimes.setdefault(key, NotificationRuntime())
