"""Application-owned wakeups for authorized, newly committed business changes."""
import asyncio
import logging

from backend.app.application.memory.sources.delivery_service import MemoryDeliveryService
from backend.app.core.errors import SerenitaError
from backend.app.application.memory.processing.task_runtime import MemoryTaskRuntime
from backend.app.application.memory.indexing.index_service import MemoryIndexService
from backend.app.repositories.memory.sources.source_deletions import deletion_recovery_cursor, recover_registered_deletions

log = logging.getLogger(__name__)


class MemoryScheduler:
    def __init__(self, memory, *, interval_seconds=5):
        self.memory = memory
        self.delivery = MemoryDeliveryService(memory)
        self.interval_seconds = interval_seconds
        self.tasks = MemoryTaskRuntime(memory)
        self.index = MemoryIndexService(memory)
        from backend.app.repositories.memory.scope_repository import MemoryScopeRepository
        self.scopes = MemoryScopeRepository(memory.members)
        self._last_queue = None
        self._deletion_recovery_cursors = {}
        self._memory_status_cursors = {}

    def step(self):
        results = []
        # Only committed deletion registrations are retried here. This access
        # control work remains necessary when all formation scopes are stopped.
        if self.memory.paths.auth_db.exists():
            actors = self.scopes.accounts()
            data_root = str(self.memory.paths.root.resolve())
            self._deletion_recovery_cursors = {actor: cursor for actor, cursor in self._deletion_recovery_cursors.items()
                if actor in actors and cursor.data_root == data_root}
            for actor in actors:
                try:
                    cursor = self._deletion_recovery_cursors.setdefault(actor, deletion_recovery_cursor(self.memory.paths, actor))
                    outcome = recover_registered_deletions(self.memory.paths, actor, cursor=cursor)
                    self._deletion_recovery_cursors[actor] = outcome.pop('cursor')
                    if outcome['deliveries'] or outcome['database_failures']:
                        results.append({'source_account_id': actor, 'source_deletions': outcome})
                except SerenitaError as exc:
                    if exc.kind not in {'forbidden', 'missing'}:
                        log.warning('Memory deletion recovery unavailable: %s', exc.code)
                except Exception:
                    log.exception('Memory deletion recovery interrupted')
        for actor, member in self.scopes.owners():
            try:
                from backend.app.repositories.business_memory_status_repository import BusinessMemoryStatusRepository
                statuses = BusinessMemoryStatusRepository(self.memory.paths)
                statuses.apply_settings(actor, member)
                key = (actor, member)
                self._memory_status_cursors[key] = statuses.recover(actor, member, self._memory_status_cursors.get(key))
                result = self.delivery.process_member(actor, member)
                if result['deliveries']:
                    results.append({'member_id': member, **result})
            except SerenitaError as exc:
                if exc.kind not in {'forbidden', 'missing'}:
                    log.warning('Memory delivery unavailable: %s', exc.code)
            except Exception:
                log.exception('Memory delivery interrupted')
        return results

    async def run(self):
        try:
            while True:
                try:
                    await asyncio.to_thread(self.step)
                    jobs = await asyncio.to_thread(self.task_jobs)
                    for job in jobs:
                        await asyncio.to_thread(self.run_job, *job)
                except Exception:
                    log.exception('Memory scheduler interrupted')
                await asyncio.sleep(self.interval_seconds)
        finally:
            self.tasks.cancel_active()

    def task_jobs(self):
        queues, seen = {}, set()

        def add(kind, actor, member, task):
            identity = task['attempt_id'] if isinstance(task, dict) else task
            key = (actor, member, identity)
            if key not in seen:
                seen.add(key)
                queues.setdefault((kind, actor, member), []).append((actor, member, task))

        scopes = []
        for owner, member in self.scopes.owners():
            scopes.append((owner, member))
            for job in self.index.pending_recoveries(owner, member, limit=1):
                add('vector_index', owner, member, job)
        for actor, member in scopes:
            for attempt in self.tasks.pending(actor, member, limit=1):
                if self.memory.settings(actor, member)['formation_state'] != 'enabled':
                    continue
                add(attempt['task_kind'], actor, member, attempt['attempt_id'])
        # Dispatch one job at a time and rotate registered queues between jobs.
        keys = sorted(queues)
        if self._last_queue is not None:
            keys = [key for key in keys if key > self._last_queue] + [key for key in keys if key <= self._last_queue]
        if not keys:
            return []
        self._last_queue = keys[0]
        return [queues[keys[0]][0]]

    def run_job(self, actor, member, attempt):
        try:
            if isinstance(attempt, dict):
                return self.tasks.run_index_recovery(actor, member, attempt)
            return self.tasks.run(actor, member, attempt)
        except SerenitaError as exc:
            # Another worker may have claimed the same immutable predecessor.
            return {'attempt_id': attempt['attempt_id'] if isinstance(attempt, dict) else attempt,
                    'status': 'unavailable', 'error_code': exc.code}
