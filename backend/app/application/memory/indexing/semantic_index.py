"""Program-owned SAG entity index delivery through Service → Repository."""
from contextlib import contextmanager, ExitStack
from hashlib import sha256
from backend.app.schemas.memory.append import stable_memory_id
from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.vectors import fail
from backend.app.repositories.memory.indexing.semantic_index_repository import MemorySemanticIndexRepository


class MemorySemanticIndexService:
    def __init__(self, index):
        self.index = index
        self.repo = index.memory.repository
        self.repository = MemorySemanticIndexRepository(self.repo)


    @contextmanager
    def _registered_target(self, actor, member, operation_id, entity_id, *,
                           event_id=None, name_id=None, model_id=None):
        """Keep ownership until delivery; pass this execution's state directly."""
        self.index.vector_models.check_running()
        target = self.repository.delivery_target(actor, member, entity_id, event_id=event_id, name_id=name_id)
        account, text, basis, kind = (target[key] for key in ('account_id', 'text', 'basis', 'kind'))
        model_id = model_id or self.index.vector_models.default_model_id(account)
        if model_id is None:
            fail('MEMORY_EMBEDDING_MODEL_REQUIRED', '实体索引需要健康档案所有者的文本向量模型。')
        space = self.index.vector_models.space(account, member, model_id)
        identity = lambda kind, label: stable_memory_id(member, operation_id, kind, label)
        binding = {'binding_id': identity('semantic_binding', 'binding'), 'entity_id': entity_id,
            'event_id': event_id, 'name_id': name_id,
            'space_id': space['space_id'], 'vector_id': identity('semantic_vector', 'vector'),
            'index_kind': kind, 'text_hash': sha256(text.encode()).hexdigest()}
        initial = {'binding_id': binding['binding_id'], 'status_id': identity('semantic_status', 'initial'), 'state': 'pending'}
        command = dict(binding)
        with self.repository.vectors.binding_guard(account, binding['binding_id'], check_running=self.index.vector_models.check_running):
            # One pending commit owns both the target and its exact space.
            batch = {
                'semantic_vector_bindings': [binding], 'semantic_vector_statuses': [initial]}
            with self.repo.members.access_guard(actor, member, write=True):
                registered = self.repository.binding(actor, member, binding['binding_id'])
                fresh = registered is None
                if registered is not None:
                    if any(registered[key] != value for key, value in binding.items() if not (key == 'event_id' and kind == 'entity_name')):
                        fail('MEMORY_OPERATION_CONFLICT', '同一实体索引操作的目标、文本或模型空间不同。', kind='conflict')
                else:
                    if not self.repository.space_exists(actor, member, space['space_id']):
                        batch['vector_spaces'] = [space]
                    self.repo.write(actor, member, operation_id + ':pending', batch, command=command)
                    registered = {**binding, 'event_id': basis, 'status': initial}
            row = registered
            binding = {**binding, 'event_id': row['event_id'], ('name' if kind == 'entity_name' else 'description'): text}
            status = row['status']
            if status['state'] == 'confirmed':
                yield {'binding_id': binding['binding_id'], 'status': status, 'replayed': True}, None
                return
            def append_status(state, **fields):
                item = {'binding_id': binding['binding_id'], 'status_id': identity('semantic_status', status['status_id'] + ':' + state),
                    'previous_status_id': status['status_id'], 'state': state, **fields}
                self.repo.write(actor, member, operation_id + ':' + item['status_id'],
                    {'semantic_vector_statuses': [item]})
                return item
            if not self.index.retry_failed and not fresh:
                if status['state'] == 'pending':
                    status = append_status('failed', error_code='MEMORY_VECTOR_DELIVERY_INTERRUPTED',
                                           error_message='前次向量交付已中断。')
                yield {'binding_id': binding['binding_id'], 'status': status, 'replayed': True}, None
                return
            if status['state'] == 'failed':
                status = append_status('pending')
            stored_vectors = [] if fresh else self.repository.vectors.rows(
                account, space, binding['vector_id'], index_kind=kind)

            def deliver(prepared=None):
                nonlocal status
                try:
                    self.index.vector_models.check_running()
                    existing = stored_vectors
                    if existing:
                        if len(existing) != 1:
                            fail('MEMORY_VECTOR_UNCONFIRMED', '实体绑定必须对应唯一向量。')
                        digest = existing[0]['vector_hash']
                        self.repository.vectors.verify_row(account, member, binding, space, digest, existing[0])
                    else:
                        if prepared is not None:
                            if 'error' in prepared:
                                raise prepared['error']
                            if prepared['space'] != space or prepared['text'] != text:
                                fail('MEMORY_VECTOR_SPACE_CHANGED', '批量向量与当前文本或模型空间不一致。')
                            vector = prepared['vector']
                        else:
                            vector = self.index.vector_models.embed(account, member, space, text)
                        # Recheck this target after external work; the commit below
                        # validates current permissions and the status transition.
                        self.index.vector_models.check_running()
                        self.repository.require_targets(actor, member, [binding])
                        digest = self.repository.vectors.add(account, member, binding, space, vector)
                    self.index.vector_models.check_running()
                    status = append_status('confirmed', vector_hash=digest)
                except SerenitaError as exc:
                    # No exception text or failed vector is used as a substitute.
                    self.index.vector_models.check_running()
                    status = append_status('failed', error_code=exc.code, error_message='实体向量交付失败。')
                return {'binding_id': binding['binding_id'], 'status': status, 'replayed': False}
            yield {'account_id': account, 'binding': binding, 'space': space, 'status': status, 'stored_vector': bool(stored_vectors)}, deliver

    def index_targets(self, actor, member, targets):
        # Repeated entities across events also reuse this call's result, even
        # when their positions would fall in different embedding batches.
        unique = {}
        for target in targets:
            operation = target['operation_id']
            if operation in unique and unique[operation] != target:
                fail('MEMORY_OPERATION_CONFLICT', '同一批实体索引操作的目标不同。', kind='conflict')
            unique[operation] = target
        results = dict(zip(unique, self._index_targets(actor, member, list(unique.values()))))
        return [results[target['operation_id']] for target in targets]

    def _index_targets(self, actor, member, targets):
        """Generate a bounded batch, then independently confirm every binding."""
        results = []
        for offset in range(0, len(targets), 10):
            batch = targets[offset:offset + 10]
            with ExitStack() as stack:
                registered = {}
                # Deterministic lock order avoids overlapping-batch deadlocks.
                for target in sorted(batch, key=lambda row: row['operation_id']):
                    operation = target['operation_id']
                    registered[operation] = (target, stack.enter_context(
                        self._registered_target(actor, member, **target)))
                pending = [registered[target['operation_id']][1][0] for target in batch]
                for row in pending:
                    if row['status']['state'] == 'failed':
                        fail(row['status'].get('error_code') or 'MEMORY_INDEX_UNCONFIRMED',
                             row['status'].get('error_message') or '实体向量保存失败。')
                groups = {}
                for position, row in enumerate(pending):
                    if row['status']['state'] != 'confirmed' and not row['stored_vector']:
                        groups.setdefault(row['space']['space_id'], []).append(position)
                prepared = {}
                for positions in groups.values():
                    space = pending[positions[0]]['space']
                    bindings = [pending[position]['binding'] for position in positions]

                    def guard():
                        self.index.vector_models.check_running()
                        self.repository.require_targets(actor, member, bindings, formation=True)

                    texts = [binding['name'] if binding['index_kind'] == 'entity_name' else binding['description'] for binding in bindings]
                    try:
                        vectors = self.index.vector_models.embed_many(pending[positions[0]]['account_id'], member, space, texts, guard=guard)
                        prepared.update({position: {'space': space, 'text': text, 'vector': vector}
                                         for position, text, vector in zip(positions, texts, vectors)})
                    except SerenitaError as exc:
                        if exc.kind in {'forbidden', 'missing', 'timeout'}:
                            raise
                        # A failed batch is audited by the model-call observer.
                        # Pass the failure too; do not repeat the provider request.
                        prepared.update({position: {'error': exc} for position in positions})
                for position, target in enumerate(batch):
                    result = pending[position]
                    if result['status']['state'] != 'confirmed':
                        result = registered[target['operation_id']][1][1](prepared.get(position))
                        pending[position] = result
                    results.append(result)
                    if result['status']['state'] != 'confirmed':
                        fail(result['status'].get('error_code') or 'MEMORY_INDEX_UNCONFIRMED',
                             result['status'].get('error_message') or '实体向量保存失败。')
        return results
