"""Deliver SAG source-fragment vectors with resumable append-only confirmations."""
from copy import deepcopy
from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.vectors import fail
from backend.app.repositories.memory.indexing.chunk_index_repository import MemoryChunkIndexRepository
from backend.app.schemas.memory.append import stable_memory_id


class MemoryChunkIndexService:
    def __init__(self, index):
        self.index = index
        self.repo = index.memory.repository
        self.repository = MemoryChunkIndexRepository(self.repo)

    def index_event(self, actor, member, event_id, *, space, delivery_results=None, source_parts=None):
        self.index.vector_models.check_running()
        chunks = self.repository.event_chunks(actor, member, event_id, source_parts=source_parts)
        results = []
        for chunk in chunks:
            key = (actor, member, space['space_id'], chunk['chunk_id'])
            if delivery_results is None or key not in delivery_results:
                result = self._deliver(actor, member, chunk, space)
                if delivery_results is not None:
                    delivery_results[key] = deepcopy(result)
            else:
                result = deepcopy(delivery_results[key])
            results.append(result)
            if result['status']['state'] != 'confirmed':
                fail(result['status'].get('error_code') or 'MEMORY_INDEX_UNCONFIRMED',
                     result['status'].get('error_message') or '原文片段向量保存失败。')
        return results

    def _deliver(self, actor, member, chunk, space):
        operation = 'sag-chunk-' + chunk['chunk_id'] + '-' + space['space_id']
        identity = lambda kind, label: stable_memory_id(member, operation, kind, label)
        binding = {key: value for key, value in chunk.items() if key != 'content'}
        binding.update(binding_id=identity('chunk_binding', 'binding'), vector_id=identity('chunk_vector', 'vector'), space_id=space['space_id'])
        initial = {'binding_id': binding['binding_id'], 'status_id': identity('chunk_status', 'initial'), 'state': 'pending'}
        with self.repo.members.access_guard(actor, member) as access:
            account = access.account_id
        with self.repository.vectors.binding_guard(account, binding['binding_id'], check_running=self.index.vector_models.check_running):
            self.index.registry.require_formation_scope(actor, member, chunk['event_id'])
            # Multiple events can cite the same fragment. Its immutable vector
            # keeps the first evidenced event and is delivered only once.
            registered = self.repository.snapshot(actor, member, binding_ids=[binding['binding_id']])['bindings']
            fresh = not registered
            if registered:
                row = registered[0]
                if any(row[key] != value for key, value in binding.items() if key != 'event_id'):
                    fail('MEMORY_CHUNK_IDENTITY_MISMATCH', '同一原文片段索引的来源、范围或空间不一致。')
                binding = {key: row[key] for key in binding}
            else:
                self.repo.write(actor, member, operation + ':pending', {
                    'chunk_vector_bindings': [binding], 'chunk_vector_statuses': [initial]})
                row = {**binding, 'content': chunk['content'], 'status': initial}

            def check_scope():
                self.index.vector_models.check_running()
                self.index.registry.require_formation_scope(actor, member, chunk['event_id'])
                self.repo.evidence.check_changes(actor, member,
                    [{key: binding[key] for key in ('source_database', 'change_id', 'field_path')}])

            status = row['status']
            if status['state'] == 'confirmed':
                return {'chunk_id': chunk['chunk_id'], 'binding_id': binding['binding_id'], 'status': status, 'replayed': True}

            def append_status(state, **fields):
                item = {'binding_id': binding['binding_id'], 'status_id': identity('chunk_status', status['status_id'] + ':' + state),
                    'previous_status_id': status['status_id'], 'state': state, **fields}
                self.repo.write(actor, member, operation + ':' + item['status_id'], {
                    'chunk_vector_statuses': [item]})
                return item

            if not self.index.retry_failed and not fresh:
                if status['state'] == 'pending':
                    status = append_status('failed', error_code='MEMORY_VECTOR_DELIVERY_INTERRUPTED',
                                           error_message='前次向量交付已中断。')
                return {'chunk_id': chunk['chunk_id'], 'binding_id': binding['binding_id'], 'status': status, 'replayed': True}
            if status['state'] == 'failed':
                status = append_status('pending')
            try:
                existing = [] if fresh else self.repository.vectors.rows(account, space, binding['vector_id'])
                if existing:
                    if len(existing) != 1:
                        fail('MEMORY_VECTOR_UNCONFIRMED', '绑定必须对应唯一且完整的实际向量行。')
                    digest = existing[0]['vector_hash']
                    self.repository.vectors.verify_row(account, member, row, space, digest, existing[0])
                else:
                    vector = self.index.vector_models.embed(account, member, space, row['content'])
                    check_scope()
                    digest = self.repository.vectors.add(account, member, row, space, vector)
                check_scope()
                status = append_status('confirmed', vector_hash=digest)
            except Exception as exc:
                check_scope()
                code = exc.code if isinstance(exc, SerenitaError) else 'MEMORY_CHUNK_VECTOR_WRITE_FAILED'
                message = exc.message if isinstance(exc, SerenitaError) else f'原文片段向量追加或确认失败（{type(exc).__name__}）。'
                status = append_status('failed', error_code=code, error_message=message)
            return {'chunk_id': chunk['chunk_id'], 'binding_id': binding['binding_id'], 'status': status, 'replayed': False}
