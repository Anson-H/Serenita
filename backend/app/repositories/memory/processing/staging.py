"""Per-change working memory. Draft facts are published only after full success."""
from contextlib import contextmanager
from copy import deepcopy
import logging
import sqlite3

from backend.app.core.errors import SerenitaError
from backend.app.core.time import local_now
from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA, MEMORY_OBJECTS

from backend.app.storage.sqlite import CommitConnection

# Recovery audit is authoritative runtime data, excluded from all staged views and publication.
STAGING_TABLES = tuple(table for table in MEMORY_DATABASE_SCHEMA.tables if table.name != "recovery_records")







def key(table, row):
    return tuple(row[name] for name in table.primary_key)


class MemoryStaging:
    def __init__(self, repo, actor, member, attempt_id, *, work_store=None):
        from backend.app.repositories.memory.processing.checkpoints import WorkStore
        self.repo, self.actor, self.member, self.attempt_id = repo, actor, member, attempt_id
        self.work = work_store or WorkStore(repo, actor, member, attempt_id)
        if (self.work.repo is not repo or
                (self.work.actor, self.work.member, self.work.attempt_id) != (actor, member, attempt_id)):
            raise SerenitaError('forbidden', 'MEMORY_WORK_SCOPE', '工作区与当前处理的成员或标识不一致。')
        self._owns_work = work_store is None
        self.published = self.work.published
        self.operational_commits = set(self.work.get('_operational_commits', []))
        self.vectors = {}
        self.defer_traces = False
        self._skip_flush = False
        try:
            self._build_view()
            from backend.app.repositories.memory.processing.staging_vectors import restore_vectors
            restore_vectors(self)
        except BaseException:
            if hasattr(self, 'db'):
                self.db.close()
            if self._owns_work:
                self.work.close()
            raise

    def checkpoint_operation_ids(self):
        return [row[0] for row in self.db.execute('SELECT operation_id FROM commits ORDER BY sequence')
            if row[0].startswith('pipeline-' + self.attempt_id)]

    def _build_view(self):
        from backend.app.repositories.memory.processing.checkpoints import formal_dependencies, conflict
        self.db = sqlite3.connect(':memory:', factory=CommitConnection)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        MEMORY_DATABASE_SCHEMA.create(self.db)
        self.original = {}
        # This is a scoped, disposable query view, never a backup or a second
        # durable memory database. It contains only the member being processed.
        with published_memory(), self.repo._transaction(self.actor, self.member) as (access, source):
            self.account = access.account_id
            if not self.published and formal_dependencies(source, self.account, self.member) != self.work.get('_formal_dependencies'):
                raise conflict()
            self.db.execute('PRAGMA defer_foreign_keys=ON')
            for table in STAGING_TABLES:
                condition = " AND COALESCE(json_extract(payload_json,'$.stream_status'),'')!='streaming'" if table.name == 'execution_entries' else ''
                rows = [dict(row) for row in source.execute(
                    f'SELECT * FROM {table.name} WHERE account_id=? AND member_id=?' + condition,
                    (self.account, self.member))]
                self.original[table.name] = {key(table, row): row for row in rows}
                if rows:
                    self.db.executemany(f"INSERT INTO {table.name} ({','.join(table.column_names)}) VALUES ({','.join('?' for _ in table.columns)})",
                        [tuple(row[name] for name in table.column_names) for row in rows])
            if not self.published:
                self._overlay()
            self.db.commit()
        self.base_commit_ids = {row['commit_id'] for row in self.original['commits'].values()}

    def _overlay(self):
        delta = self.work.get('_delta', {})
        needed_commits = set()
        for table in STAGING_TABLES:
            if table.name in {'commits', 'processing_steps', 'execution_entries'}:
                continue
            for row in delta.get(table.name, []):
                if table.name == 'processing_attempts' and key(table, row) in self.original[table.name]:
                    continue
                needed_commits.update(row[field] for field in ('commit_id', 'started_commit_id', 'updated_commit_id')
                    if row.get(field))
        sequence = self.db.execute('SELECT COALESCE(max(sequence),0) FROM commits').fetchone()[0]
        for table in STAGING_TABLES:
            if table.name == 'processing_steps':
                # The same logical step has a fresh progress_id on each save.
                # Its live running/failed record remains authoritative on reopen;
                # the runtime records final completion again before publication.
                continue
            rows = delta.get(table.name, [])
            if table.name == 'commits':
                # Completion/step-only commits must be recreated against the
                # live running attempt. Keeping their idempotency receipts with
                # no corresponding update would falsely replay completion.
                rows = sorted((row for row in rows if row['commit_id'] in needed_commits), key=lambda row: row['sequence'])
            for row in rows:
                previous = self.original[table.name].get(key(table, row))
                if previous is not None:
                    if table.name == 'processing_attempts':
                        continue
                    if table.mutable_columns:
                        fields = table.mutable_columns
                        self.db.execute(f"UPDATE {table.name} SET {','.join(name+'=?' for name in fields)} "
                            f"WHERE {' AND '.join(name+'=?' for name in table.primary_key)}",
                            [row[name] for name in fields] + list(key(table, row)))
                    continue
                if table.name == 'commits':
                    sequence += 1
                    row = {**row, 'sequence': sequence}
                self.db.execute(f"INSERT INTO {table.name} ({','.join(table.column_names)}) "
                    f"VALUES ({','.join('?' for _ in table.columns)})", [row[name] for name in table.column_names])

    def _delta(self):
        result = {}
        for table in STAGING_TABLES:
            if table.name == 'execution_entries' or table.name == 'processing_steps' and not self.defer_traces:
                continue
            rows = [dict(row) for row in self.db.execute(f'SELECT * FROM {table.name}')]
            changed = [row for row in rows if row['commit_id'] not in self.operational_commits
                and row != self.original[table.name].get(key(table, row))]
            if changed:
                result[table.name] = changed
        return result

    def flush(self):
        with self.work.transaction():
            self.work.put('_delta', self._delta())
            self.work.put('_operational_commits', sorted(self.operational_commits))

    def checkpoint(self, key, value):
        """Save successful app state and its memory deltas in one durable commit."""
        with self.work.transaction():
            self.flush()
            self.work.put(key, value)
            current = {'step_id': key.split(':', 1)[-1],
                'updated_at': local_now().isoformat(timespec='microseconds')}
            self.work.put('_checkpoint', {'key': key, 'value': value, **current})
            self.work.put('current_checkpoint', current)

    def _validate_publication(self, delta):
        """Require complete staged facts and every index binding actually planned."""
        def incomplete():
            raise SerenitaError('conflict', 'MEMORY_STAGING_INCOMPLETE', '暂存记忆的事项、版本或索引尚未完整保存。')
        attempt = self.db.execute('SELECT processing_status FROM processing_attempts WHERE attempt_id=?',
            (self.attempt_id,)).fetchone()
        if attempt is None or attempt['processing_status'] != 'completed':
            incomplete()
        for event in delta.get('events', []):
            row = self.db.execute('SELECT 1 FROM event_episode m JOIN episode_revisions r '
                'ON r.episode_id=m.episode_id AND r.trigger_event_id=m.event_id WHERE m.event_id=?',
                (event['event_id'],)).fetchone()
            if row is None:
                incomplete()
        index_tables = {'event_vectors': 'event_vector_statuses', 'source_chunks': 'source_chunk_statuses',
            'entity_vectors': 'entity_vector_statuses', 'event_entity_vectors': 'event_entity_vector_statuses'}
        for table, statuses in index_tables.items():
            for binding in delta.get(table, []):
                latest = self.db.execute(f'SELECT s.* FROM {statuses} s JOIN commits c ON c.commit_id=s.commit_id '
                    'WHERE s.binding_id=? ORDER BY c.sequence DESC LIMIT 1', (binding['binding_id'],)).fetchone()
                vector = self.vectors.get((table, binding['space_id']), {}).get('rows', {}).get(binding['vector_id'])
                if latest is None or latest['state'] != 'confirmed' or vector is None or vector['vector_hash'] != latest['vector_hash']:
                    incomplete()
        for (table, _), group in self.vectors.items():
            for vector_id in group['rows']:
                if not self.db.execute(f'SELECT 1 FROM {table} WHERE vector_id=?', (vector_id,)).fetchone():
                    incomplete()

    def __enter__(self):
        self.token = _active.set(self)
        return self

    def __exit__(self, *error):
        _active.reset(self.token)
        self.db.close()
        self.vectors.clear()
        if self._owns_work:
            self.work.close()

    @contextmanager
    def transaction(self, access, *, write):
        from backend.app.repositories.memory.reading.read_cache import immutable_read_scope
        from backend.app.repositories.memory.transaction import memory_transaction_scope
        nested = self.db.in_transaction
        if not nested:
            self.db.execute('BEGIN')
            self.db._commit_effects = {}
        try:
            with memory_transaction_scope(self.db, access), immutable_read_scope(self.db, access, write=write) as cache:
                yield self.db
                if cache is not None:
                    self.repo._recheck_read_sources(self.db, access, cache)
            if not nested:
                self.db.commit()
                if write and not self._skip_flush:
                    self.flush()
                callbacks = tuple(self.db._commit_effects.values())
                self.db._commit_effects = {}
                for callback in callbacks:
                    callback()
        except BaseException:
            if not nested:
                self.db.rollback()
                self.db._commit_effects = {}
                # A failed durable commit must not leave successful-looking
                # memory in the disposable view used by an automatic retry.
                if write and not self._skip_flush:
                    self.db.close()
                    self._build_view()
            raise

    def existing_reference(self, ref):
        from backend.app.domain.memory.references import DETAIL_REFERENCES, VERSION_REFERENCES
        table, primary = MEMORY_OBJECTS[ref['object_type']]
        if ref['object_type'] in DETAIL_REFERENCES:
            identity = (ref['object_id'], ref.get('item_id'))
        elif ref['object_type'] in VERSION_REFERENCES:
            identity = (ref['object_id'], ref.get('version'))
        else:
            identity = (ref['object_id'],)
        return identity in self.original[table]

    def write(self, operation_id, batch, **options):
        from backend.app.schemas.memory.append import MemoryWrite
        data = batch.model_dump(mode='json') if isinstance(batch, MemoryWrite) else deepcopy(batch)
        sequence = self.db.execute('SELECT COALESCE(max(sequence),0)+1 FROM commits').fetchone()[0]
        for entry in data.get('execution_entries', []):
            entry['payload'] = {**entry['payload'], 'draft_scope': self.attempt_id, 'draft_sequence': sequence}
        operational_only = bool(data) and all(name in {'execution_entries', 'processing_steps'} or not value
            for name, value in data.items()) and not self.defer_traces
        previous_skip = self._skip_flush
        self._skip_flush = previous_skip or operational_only
        try:
            result = self.repo._write(self.actor, self.member, operation_id, data, **options)
        finally:
            self._skip_flush = previous_skip
        operational = {name: data[name] for name in ('execution_entries', 'processing_steps') if data.get(name)}
        if operational and not self.defer_traces:
            # Live traces are durable observations, not formal memory. Draft
            # objects are described in their payload, never as durable pointers.
            for entry in operational.get('execution_entries', []):
                entry['dependencies'] = [ref for ref in entry['dependencies'] if self.existing_reference(ref)]
            with published_memory():
                actual = self.repo._write(self.actor, self.member, operation_id, operational)
            self.operational_commits.add(actual['commit_id'])
        return result

    def publish(self, *, check_running, references, token):
        from backend.app.repositories.memory.processing.checkpoints import formal_dependencies, conflict
        from backend.app.repositories.memory.processing.staging_vectors import publish_vectors
        from backend.app.repositories.business_memory_status_repository import BusinessMemoryStatusRepository
        if self.published:
            from backend.app.repositories.memory.processing.staging_vectors import journal_path
            task = self.original['processing_attempts'][(self.attempt_id,)]
            with published_memory():
                BusinessMemoryStatusRepository(self.repo.paths).sync(self.account, self.member,
                    {(task['source_database'], task['change_id'])})
            journal_path(self.repo.paths, self.account, self.attempt_id).unlink(missing_ok=True)
            self.work.remove()
            return
        check_running()
        self.flush()
        delta = {}
        for table in STAGING_TABLES:
            delta[table.name] = [dict(row) for row in self.db.execute(f'SELECT * FROM {table.name}')
                if key(table, row) not in self.original[table.name]]
        self._validate_publication(delta)
        updates = []
        for table in STAGING_TABLES:
            if not table.mutable_columns:
                continue
            for raw in self.db.execute(f'SELECT * FROM {table.name}'):
                row = dict(raw)
                previous = self.original[table.name].get(key(table, row))
                if previous is not None and row != previous:
                    updates.append((table, previous, row))
        # This receipt is durable before vectors or formal SQLite are touched.
        # Its commit identities resolve the crash after SQLite commit precisely.
        self.work.put('_publication', {'commit_ids': [row['commit_id'] for row in delta['commits']
            if row['commit_id'] not in self.operational_commits]})
        with published_memory(), token.commit_guard(), publish_vectors(self):
            with self.repo._transaction(self.actor, self.member, write=True) as (access, db):
                current = self.repo._require(db, access, 'processing_attempt', self.attempt_id)
                if current['processing_status'] != 'running':
                    raise SerenitaError('conflict', 'MEMORY_EXECUTION_CANCELLED', '当前处理已停止，暂存内容不能提交。')
                if self.repo._settings(db, access)['formation_state'] != 'enabled':
                    raise SerenitaError('forbidden', 'MEMORY_FORMATION_PAUSED', '自动记忆形成已暂停，暂存内容不能提交。')
                for ref in references:
                    if self.existing_reference(ref):
                        self.repo._require(db, access, ref['object_type'], ref['object_id'],
                            item_id=ref.get('item_id'), version=ref.get('version'))
                # Inputs were judged against this member's formal memory at
                # start. Reject another formal writer rather than silently
                # publishing judgments against a different history.
                if formal_dependencies(db, self.account, self.member) != self.work.get('_formal_dependencies'):
                    raise conflict()
                db.execute('PRAGMA defer_foreign_keys=ON')
                sequence = db.execute('SELECT COALESCE(max(sequence),0) FROM commits').fetchone()[0]
                published_at = local_now().isoformat(timespec='microseconds')
                for row in sorted(delta['commits'], key=lambda row: row['sequence']):
                    if row['commit_id'] in self.operational_commits:
                        continue
                    sequence += 1
                    self.repo._insert(db, 'commits', {**row, 'sequence': sequence, 'submitted_at': published_at})
                for table in STAGING_TABLES:
                    if table.name in {'commits', 'execution_entries'}:
                        continue
                    for row in delta[table.name]:
                        if row['commit_id'] in self.operational_commits:
                            continue
                        self.repo._insert(db, table.name, row)
                for table, previous, row in updates:
                    fields = table.mutable_columns
                    where = ' AND '.join(name+'=?' for name in table.primary_key)
                    args = [row[name] for name in fields] + list(key(table, row))
                    if table.name == 'processing_attempts':
                        where += ' AND updated_commit_id=?'
                        args.append(previous['updated_commit_id'])
                    changed = db.execute(f"UPDATE {table.name} SET {','.join(name+'=?' for name in fields)} WHERE {where}", args)
                    if changed.rowcount != 1:
                        raise SerenitaError('conflict', 'MEMORY_ATTEMPT_CONFLICT', '处理状态已变化，暂存内容不能提交。')
                if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise sqlite3.IntegrityError('Staged memory contains an invalid reference')
            # The repository's permission checks and SQLite commit have both
            # completed. Cleanup failures cannot undo this successful result.
            self.published = True
        task = self.original['processing_attempts'][(self.attempt_id,)]
        BusinessMemoryStatusRepository(self.repo.paths).sync(self.account, self.member,
            {(task['source_database'], task['change_id'])})
        try:
            self.work.remove()
        except OSError:
            logging.getLogger(__name__).exception('Could not remove published memory work')

from backend.app.repositories.memory.processing.staging_scope import _active, published_memory
