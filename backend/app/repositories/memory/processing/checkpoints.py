"""Durable, short SQLite transactions for one member's generation attempt."""
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3

from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import canonical_uuid
from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA
from backend.app.storage.memory.work_database import MEMORY_WORK_DATABASE_SCHEMA


NON_FORMAL = frozenset({'commits', 'processing_attempts', 'processing_steps',
    'execution_entries', 'vector_requests', 'settings_history', 'access_restrictions', 'recovery_records'})




def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def formal_dependencies(db, account, member):
    """Identity and content hashes only; mutable execution state is excluded."""
    result = {}
    for table in MEMORY_DATABASE_SCHEMA.tables:
        if table.name in NON_FORMAL:
            continue
        rows = [] if db is None else db.execute(
            f"SELECT * FROM {table.name} WHERE account_id=? AND member_id=? ORDER BY {','.join(table.primary_key)}",
            (account, member))
        result[table.name] = [[list(row[name] for name in table.primary_key),
            hashlib.sha256(encoded(dict(row)).encode()).hexdigest()] for row in rows]
    return result


def conflict():
    return SerenitaError('conflict', 'MEMORY_DRAFT_CONFLICT',
        '正式记忆已变化，已保存的暂存内容不能继续使用，请从头重试。')




class WorkStore:
    def request_counts(self):
        return {row[0]: json.loads(row[1]) for row in self.db.execute(
            "SELECT key,value_json FROM work_values WHERE key LIKE 'budget:%'")}

    def __init__(self, repo, actor, member, attempt_id):
        from backend.app.repositories.memory.processing.staging_scope import published_memory
        self.repo, self.actor, self.member = repo, actor, canonical_uuid(member)
        self.attempt_id = canonical_uuid(attempt_id)
        self.db = None
        self._depth = 0
        with published_memory(), repo._transaction(actor, member) as (access, formal):
            repo._require(formal, access, 'processing_attempt', attempt_id)
            self.account = access.account_id
            self.path = work_path(repo.paths, self.account, member, attempt_id)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            MEMORY_WORK_DATABASE_SCHEMA.validate_existing(self.path)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            self.db.execute('PRAGMA synchronous=FULL')
            try:
                with self.transaction():
                    MEMORY_WORK_DATABASE_SCHEMA.create(self.db)
                    identity = {'account_id': self.account, 'member_id': member, 'attempt_id': attempt_id}
                    previous = self.get('_identity')
                    if previous is None:
                        self.put('_identity', identity)
                        self.put('generation_id', attempt_id)
                        self.put('_formal_dependencies', formal_dependencies(formal, self.account, member))
                    elif previous != identity:
                        raise conflict()
                    self.published = publication_committed(formal, self.account, member, self.get('_publication'))
                    if not self.published and self.get('_formal_dependencies') != formal_dependencies(formal, self.account, member):
                        raise conflict()
                # Persist each new directory entry as well as SQLite contents.
                for directory in (self.path.parent, self.path.parent.parent, self.path.parent.parent.parent):
                    descriptor = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            except BaseException:
                self.close()
                raise

    def get(self, key, default=None):
        row = self.db.execute('SELECT value_json FROM work_values WHERE key=?', (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def exists(self, key=None):
        if key is None:
            return self.path.is_file()
        return self.db.execute('SELECT 1 FROM work_values WHERE key=?', (key,)).fetchone() is not None

    def put(self, key, value):
        payload = encoded(value)
        with self.transaction():
            self.db.execute('INSERT INTO work_values (key,value_json) VALUES (?,?) '
                'ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json', (key, payload))

    @contextmanager
    def transaction(self):
        """Nest with savepoints; no lock survives the caller's short transaction."""
        depth = self._depth
        name = f'work_{depth}'
        self.db.execute('BEGIN IMMEDIATE' if depth == 0 else f'SAVEPOINT {name}')
        self._depth += 1
        try:
            yield self
            self.db.execute('COMMIT' if depth == 0 else f'RELEASE {name}')
        except BaseException:
            if self.db.in_transaction:
                if depth == 0:
                    self.db.rollback()
                else:
                    self.db.execute(f'ROLLBACK TO {name}')
                    self.db.execute(f'RELEASE {name}')
            raise
        finally:
            self._depth -= 1

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def remove(self):
        """Called after verified formal publication or authorized explicit retry."""
        self.close()
        self.path.unlink(missing_ok=True)
        for suffix in ('-journal', '-wal', '-shm'):
            self.path.with_name(self.path.name + suffix).unlink(missing_ok=True)
        self.path.parent.rmdir()


def inspect_work(repo, actor, member, attempt_id):
    """Inspect without creating, updating or repairing a work database."""
    from backend.app.repositories.memory.processing.staging_scope import published_memory
    result = {'checkpoint': None, 'recovery_status': 'unavailable',
              'recovery_reason': '没有可继续使用的检查点，请从头重新处理。', 'available': False}
    with published_memory(), repo._transaction(actor, member) as (access, formal):
        attempt = repo._require(formal, access, 'processing_attempt', attempt_id)
        path = work_path(repo.paths, access.account_id, member, attempt_id)
        if not path.is_file():
            return result
        db = None
        try:
            MEMORY_WORK_DATABASE_SCHEMA.validate_existing(path)
            db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
            def get(key):
                row = db.execute('SELECT value_json FROM work_values WHERE key=?', (key,)).fetchone()
                return None if row is None else json.loads(row[0])
            result['checkpoint'] = get('current_checkpoint') or get('_checkpoint')
            if get('_identity') != {'account_id': access.account_id, 'member_id': member, 'attempt_id': attempt_id}:
                raise conflict()
            if publication_committed(formal, access.account_id, member, get('_publication')):
                result.update(recovery_status='published', recovery_reason=None)
            elif attempt['processing_status'] == 'failed' and (
                    attempt['model_id'] is None or attempt['started_commit_id'] is None):
                result.update(recovery_status='unavailable', recovery_reason='尚未登记执行模型，请从头重新处理。')
            elif get('_formal_dependencies') != formal_dependencies(formal, access.account_id, member):
                result.update(recovery_status='conflict', recovery_reason=conflict().message)
            elif get('recovery_code') in {'MEMORY_CHECKPOINT_CONTRACT_CHANGED', 'MEMORY_CHECKPOINT_SOURCE_CHANGED', 'MEMORY_CHECKPOINT_DAMAGED'}:
                result.update(recovery_status='conflict', recovery_reason=get('recovery_reason') or
                    {'MEMORY_CHECKPOINT_CONTRACT_CHANGED': '执行契约已变化，请从头重新处理。',
                     'MEMORY_CHECKPOINT_SOURCE_CHANGED': '来源内容已变化，请从头重新处理。',
                     'MEMORY_CHECKPOINT_DAMAGED': '检查点内容与保存摘要不一致，请从头重新处理。'}[get('recovery_code')])
            else:
                result.update(recovery_status='available', recovery_reason=get('recovery_reason'), available=True)
        except (sqlite3.Error, ValueError, RuntimeError, SerenitaError) as error:
            result.update(recovery_status='invalid', recovery_reason=str(error))
        finally:
            if db is not None:
                db.close()
    return result


def discard_work(repo, actor, member, attempt_id):
    """Explicit fresh retry only; remove unpublished vectors before their cache."""
    from backend.app.repositories.memory.processing.staging_scope import published_memory
    from backend.app.repositories.memory.processing.staging_vectors import discard_unpublished
    with published_memory(), repo._transaction(actor, member) as (access, db):
        attempt = repo._require(db, access, 'processing_attempt', attempt_id)
        if attempt['processing_status'] not in {'failed', 'cancelled'}:
            raise SerenitaError('conflict', 'MEMORY_WORK_DISCARD_FORBIDDEN', '仅允许从头重试已失败或取消的处理。')
        path = work_path(repo.paths, access.account_id, member, attempt_id)
    discard_unpublished(repo, actor, member, attempt_id)
    if path.exists():
        path.unlink()
        for suffix in ('-journal', '-wal', '-shm'):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        path.parent.rmdir()


def cleanup_published_work(repo, actor, member):
    """Sync completed business status, then remove work under the caller's member lock."""
    from backend.app.repositories.memory.processing.staging_scope import published_memory
    from backend.app.repositories.memory.processing.staging_vectors import journal_path
    from backend.app.repositories.business_memory_status_repository import BusinessMemoryStatusRepository
    candidates = []
    removed = []
    with published_memory(), repo._transaction(actor, member) as (access, formal):
        directory = repo.paths.memory_db(access.account_id).parent.parent / 'work' / canonical_uuid(member)
        if not directory.is_dir() or formal is None:
            return removed
        for attempt_dir in directory.iterdir():
            if not attempt_dir.is_dir() or attempt_dir.is_symlink():
                continue
            try:
                attempt_id = canonical_uuid(attempt_dir.name)
            except (ValueError, SerenitaError):
                continue
            path = attempt_dir / 'work.db'
            if not path.is_file() or path.is_symlink():
                continue
            current = formal.execute('SELECT processing_status,source_database,change_id FROM processing_attempts '
                'WHERE attempt_id=? AND account_id=? AND member_id=?',
                (attempt_id, access.account_id, member)).fetchone()
            if not current or current['processing_status'] != 'completed':
                continue
            db = None
            try:
                MEMORY_WORK_DATABASE_SCHEMA.validate_existing(path)
                db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
                row = db.execute("SELECT value_json FROM work_values WHERE key='_publication'").fetchone()
                identity = db.execute("SELECT value_json FROM work_values WHERE key='_identity'").fetchone()
                if (identity is None or json.loads(identity[0]) != {'account_id': access.account_id,
                        'member_id': member, 'attempt_id': attempt_id} or row is None or
                        not publication_committed(formal, access.account_id, member, json.loads(row[0]))):
                    continue
                db.close()
                db = None
                candidates.append((access.account_id, attempt_id, path,
                    current['source_database'], current['change_id']))
            except (OSError, sqlite3.Error, ValueError, RuntimeError):
                # A damaged or busy receipt is preserved for inspection.
                continue
            finally:
                if db is not None:
                    db.close()
    # Release memory and member authorization database transactions before
    # synchronization: it writes a business database and reads formal memory.
    # The caller's formation_guard still excludes active publication for this
    # member; completed attempts and their commit identities are immutable.
    with published_memory():
        for account, attempt_id, path, source, change in candidates:
            try:
                if source is not None and change is not None:
                    BusinessMemoryStatusRepository(repo.paths).sync(account, member, {(source, change)})
                journal_path(repo.paths, account, attempt_id).unlink(missing_ok=True)
                path.unlink()
                for suffix in ('-journal', '-wal', '-shm'):
                    path.with_name(path.name + suffix).unlink(missing_ok=True)
                path.parent.rmdir()
                removed.append(attempt_id)
            except (OSError, sqlite3.Error, ValueError, RuntimeError):
                # A failed status sync retains both work and journal so the
                # next guarded cleanup retries the same idempotent repair.
                continue
    return removed


def append_recovery(repo, actor, member, attempt_id, operation_id, kind, checkpoint, retry_epoch):
    """Append immutable recovery audit in the authorized memory transaction."""
    from backend.app.core.time import local_now
    from backend.app.schemas.memory.append import stable_memory_id
    from backend.app.storage.memory.recovery_database import RECOVERY_RECORDS_TABLE
    from backend.app.repositories.memory.processing.staging_scope import published_memory
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError('恢复操作标识不能为空。')
    if kind not in {'auto', 'explicit'} or type(retry_epoch) is not int or retry_epoch < 0:
        raise ValueError('恢复类型或重试次数无效。')
    with published_memory(), repo._transaction(actor, member, write=True) as (access, db):
        repo._require(db, access, 'processing_attempt', attempt_id)
        row = {'recovery_id': stable_memory_id(member, operation_id, 'recovery', attempt_id),
            'account_id': access.account_id, 'member_id': member, 'attempt_id': attempt_id,
            'operation_id': operation_id, 'kind': kind, 'checkpoint_json': encoded(checkpoint),
            'retry_epoch': retry_epoch, 'recorded_at': local_now().isoformat(timespec='microseconds')}
        RECOVERY_RECORDS_TABLE.validate_values(row)
        previous = db.execute(
            'SELECT * FROM recovery_records WHERE account_id=? AND member_id=? AND operation_id=?',
            (access.account_id, member, operation_id),
        ).fetchone()
        if previous is not None:
            if any(previous[key] != value for key, value in row.items() if key != 'recorded_at'):
                raise SerenitaError('conflict', 'MEMORY_RECOVERY_OPERATION_CONFLICT', '相同恢复操作标识的记录内容不同。')
            row = dict(previous)
        else:
            db.execute(f"INSERT INTO recovery_records ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
    return {**{key: value for key, value in row.items() if key != 'checkpoint_json'}, 'checkpoint': json.loads(row['checkpoint_json'])}


def read_recoveries(repo, actor, member, attempt_id):
    from backend.app.repositories.memory.processing.staging_scope import published_memory
    with published_memory(), repo._transaction(actor, member) as (access, db):
        repo._require(db, access, 'processing_attempt', attempt_id)
        rows = [dict(row) for row in db.execute('SELECT * FROM recovery_records '
            'WHERE account_id=? AND member_id=? AND attempt_id=? ORDER BY recorded_at,recovery_id',
            (access.account_id, member, attempt_id))]
        for row in rows:
            row['checkpoint'] = json.loads(row.pop('checkpoint_json'))
        return rows

from backend.app.repositories.memory.processing.work_identity import publication_committed, work_path
