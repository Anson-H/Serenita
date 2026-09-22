"""Recoverable vector publication; formal SQLite determines visibility."""
from contextlib import contextmanager
import json
import logging
import os

from backend.app.schemas.memory.append import canonical_uuid


def journal_path(paths, account, attempt):
    return paths.memory_vectors_dir(account) / '.pending' / (canonical_uuid(attempt) + '.json')


def vector_stores(paths):
    from backend.app.repositories.memory.indexing.vector_store import LanceVectors
    from backend.app.repositories.memory.indexing.source_vector_store import LanceSourceChunks
    from backend.app.repositories.memory.indexing.entity_vector_store import LanceEntityVectors, LanceEventEntityVectors
    return {cls.index_name: cls(paths) for cls in
            (LanceVectors, LanceSourceChunks, LanceEntityVectors, LanceEventEntityVectors)}


def restore_vectors(stage):
    stores = vector_stores(stage.repo.paths)
    for item in stage.work.get('_vectors', []):
        stage.vectors[(item['index_name'], item['space']['space_id'])] = {
            'store': stores[item['index_name']], 'space': item['space'], 'rows': item['rows']}




def discard_unpublished(repo, actor, member, attempt):
    stores = vector_stores(repo.paths)
    with repo._transaction(actor, member, write=True) as (access, db):
        path = journal_path(repo.paths, access.account_id, attempt)
        if not path.exists():
            return
        current = db.execute('SELECT processing_status FROM processing_attempts WHERE attempt_id=? AND account_id=? AND member_id=?',
            (attempt, access.account_id, member)).fetchone()
        if current is None or current['processing_status'] not in {'failed', 'cancelled'}:
            raise RuntimeError('Only a failed attempt can discard an unpublished vector journal')
        try:
            rows = json.loads(path.read_text())
        except json.JSONDecodeError:
            from backend.app.repositories.memory.processing.work_identity import work_path
            import sqlite3
            work = work_path(repo.paths, access.account_id, member, attempt)
            connection = sqlite3.connect(work.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                receipt = connection.execute("SELECT value_json FROM work_values WHERE key='_vector_journal'").fetchone()
                if receipt is None:
                    raise RuntimeError('The damaged vector journal has no durable receipt')
                rows = json.loads(receipt[0])
            finally:
                connection.close()
        for item in rows:
            store = stores[item['index_name']]
            space = item['space']
            for identity in item['vector_ids']:
                canonical_uuid(identity)
                if db.execute(f'SELECT 1 FROM {store.index_name} WHERE vector_id=? LIMIT 1', (identity,)).fetchone():
                    raise RuntimeError('A published vector cannot be discarded')
            table = store._table(access.account_id, space)
            if table is not None:
                ids = ','.join("'" + canonical_uuid(value) + "'" for value in item['vector_ids'])
                table.delete(f'vector_id IN ({ids})')
        path.unlink()


@contextmanager
def publish_vectors(stage):
    groups = list(stage.vectors.values())
    if not groups:
        try:
            yield
        except BaseException:
            from backend.app.repositories.memory.processing.staging_scope import published_memory
            from backend.app.repositories.memory.processing.work_identity import publication_committed
            with published_memory(), stage.repo._transaction(stage.actor, stage.member) as (_, db):
                committed = publication_committed(db, stage.account, stage.member, stage.work.get('_publication'))
            if not committed:
                raise
            stage.published = True
            logging.getLogger(__name__).exception('Formal memory committed before publication follow-up failed')
        return
    path = journal_path(stage.repo.paths, stage.account, stage.attempt_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    expected = [{'index_name': group['store'].index_name, 'space': group['space'],
                 'vector_ids': sorted(group['rows'])} for group in groups]
    # The transactionally saved receipt is authoritative even if the process
    # exits while writing this small discovery file. No vector is added first.
    stage.work.put('_vector_journal', expected)
    if path.exists():
        try:
            previous = json.loads(path.read_text())
        except json.JSONDecodeError:
            previous = expected
        if previous != expected:
            raise RuntimeError('Vector publication journal differs from durable deltas')
    with path.open('w') as handle:
        os.chmod(path, 0o600)
        json.dump(expected, handle)
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    try:
        for group in groups:
            table = group['store']._table(stage.account, group['space'], create=True)
            pending = []
            for identity, row in group['rows'].items():
                identity = canonical_uuid(identity)
                actual = table.search().where(f"vector_id = '{identity}'").limit(2).to_list()
                if len(actual) > 1 or actual and actual[0] != row:
                    raise RuntimeError('Vector publication identity has conflicting content')
                if not actual:
                    pending.append(row)
            if pending:
                table.add(pending)
        yield
    except BaseException:
        # Never delete here: SQLite may have committed before a callback failed.
        # Reopening resolves the receipt and reuses already appended vectors.
        from backend.app.repositories.memory.processing.staging_scope import published_memory
        from backend.app.repositories.memory.processing.work_identity import publication_committed
        with published_memory(), stage.repo._transaction(stage.actor, stage.member) as (_, db):
            committed = publication_committed(db, stage.account, stage.member, stage.work.get('_publication'))
        if not committed:
            raise
        stage.published = True
        logging.getLogger(__name__).exception('Formal memory committed before publication follow-up failed')
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).exception('Could not remove completed vector publication journal')
    else:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).exception('Could not remove completed vector publication journal')




