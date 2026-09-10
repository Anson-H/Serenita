"""Deadline wakeups and independent bounded recovery for registered producers."""

import asyncio
import heapq
import itertools
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class ScheduledCall:
    at: float
    callback: Callable
    retry: bool = False


class NotificationScheduler:
    def __init__(self, notifications, *, producers=(), maintenance=()):
        self.service, self.runtime, self.repository = (
            notifications,
            notifications.runtime,
            notifications.repository,
        )
        self.producers, self.maintenance = list(producers), list(maintenance)
        self.heap, self.sequence = [], itertools.count()
        self.schedule_generation = -1
        self.generation = -1
        self.delivery_at = 0
        self.clock_offset = time.time() - time.monotonic()

    def push(self, job):
        if job:
            heapq.heappush(self.heap, (job.at, next(self.sequence), job))

    def step(self):
        offset = time.time() - time.monotonic()
        if abs(offset - self.clock_offset) > 0.5:
            self.schedule_generation = -1
            self.clock_offset = offset
        # Execute already-due jobs before replacing the queue. Every callback
        # validates current business state, including edits committed meanwhile.
        now = time.time()
        for _ in range(100):
            if not self.heap or self.heap[0][0] > now:
                break
            _, _, job = heapq.heappop(self.heap)
            try:
                self.push(job.callback())
            except Exception:
                log.exception("Scheduled notification failed")
                self.push(ScheduledCall(time.time() + 1, job.callback, retry=True))
        if self.schedule_generation != self.runtime.schedule_generation:
            generation = self.runtime.schedule_generation
            at = datetime.now(timezone.utc)
            jobs = []
            for producer in self.producers:
                jobs.extend(producer.jobs(at))
            # Keep failed/due callbacks until they finish; a rebuild must not
            # discard a retry that is the only remaining evidence of a failure.
            retries = [
                entry[2] for entry in self.heap if getattr(entry[2], "retry", False)
            ]
            self.heap.clear()
            for job in jobs + retries:
                self.push(job)
            self.schedule_generation = generation
        changed = self.runtime.generation != self.generation
        self.generation = self.runtime.generation
        now = time.time()
        # Outbox retries have their own deadlines.
        next_at = self.heap[0][0] if self.heap else now + 30
        if changed or now >= self.delivery_at:
            upcoming = now + 30
            for actor in self.repository.accounts():
                try:
                    self.service.dispatch(actor)
                    due = self.repository.next_delivery(actor)
                    if due:
                        upcoming = min(
                            upcoming, datetime.fromisoformat(due).timestamp()
                        )
                except Exception:
                    log.exception("Account notification delivery failed")
                    upcoming = min(upcoming, time.time() + 1)
            self.delivery_at = upcoming
        return max(
            0.001,
            min(
                1,
                next_at - time.time(),
                self.delivery_at - time.time(),
            ),
        )

    async def live(self):
        while True:
            before = self.runtime.generation
            try:
                delay = await asyncio.to_thread(self.step)
            except Exception:
                log.exception("Notification scheduler failed")
                delay = 1
            await asyncio.to_thread(self.runtime.wait, before, delay)

    def reconcile(self):
        for producer in self.producers:
            try:
                producer.recover(datetime.now(timezone.utc))
            except Exception:
                log.exception("Notification recovery failed")
        for task in self.maintenance:
            try:
                task()
            except Exception:
                log.exception("Background maintenance failed")
        for account in self.repository.accounts():
            try:
                self.service.revalidate(account)
            except Exception:
                log.exception("Notification state reconciliation failed")
        self.runtime.changed(self.repository.accounts(), reschedule=True)

    async def recovery(self):
        while True:
            await asyncio.to_thread(self.reconcile)
            await asyncio.sleep(30)

    async def run(self):
        async with asyncio.TaskGroup() as group:
            group.create_task(self.live())
            group.create_task(self.recovery())
