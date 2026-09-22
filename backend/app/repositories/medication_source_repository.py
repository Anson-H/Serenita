"""Medication-owned originals, transactional persistence and file cleanup."""

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from backend.app.core.time import local_now_iso
from backend.app.domain.medication_files import FILE_TYPES
from typing import Protocol
from contextlib import AbstractContextManager
from backend.app.storage.paths import ensure_private_directory
from backend.app.storage.sqlite import connect
from backend.app.storage.cleanup_queue import cleanup_batch, drain_cleanup_batch


class MedicationSourceCatalog(Protocol):
    """Catalog checks and transaction scope required by original-file storage."""
    account_id: str
    paths: object

    def transaction(self, write: bool = False) -> AbstractContextManager: ...
    def init_db(self) -> None: ...
    def detail(self, db, member, kind, object_id) -> dict: ...
    def insert(self, db, table, values, schema="medication_data") -> None: ...


class MedicationSourceRepository:
    def __init__(self, catalog: MedicationSourceCatalog):
        self.account_id, self.paths = catalog.account_id, catalog.paths
        self.catalog = catalog

    @contextmanager
    def staging(self):
        created = []
        try:
            yield created
        except Exception:
            # The enclosing database transaction has rolled back before this runs.
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    with self.catalog.transaction(True) as db:
                        self.catalog.insert(db, 'medication_source_cleanup_outbox', {
                            'cleanup_id': str(uuid4()), 'relative_path': path.name, 'created_at': local_now_iso(),
                        })
            raise

    def ensure(self, db, medication_id, source, position, created):
        resource_id = source['resource_id']
        stored = db.execute('SELECT * FROM medication_data.medication_sources WHERE resource_id=?', (resource_id,)).fetchone()
        if stored is not None:
            if stored['medication_id'] != medication_id:
                raise ValueError('每份药品原件只能归属一个药品，不能关联到其他药品。')
            if stored['sha256'] != source['sha256']:
                raise ValueError('来源内容已变化。')
            self.content(dict(stored))
            return resource_id
        root = ensure_private_directory(self.paths.medication_files_dir(self.account_id))
        path = root / (resource_id + FILE_TYPES[source['mime_type']])
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            created.append(path)
            stream.write(source['content'])
            stream.flush()
            os.fsync(stream.fileno())
        self.catalog.insert(db, 'medication_sources', {
            'resource_id': resource_id, 'medication_id': medication_id,
            'original_filename': Path(source['original_filename']).name or path.name,
            'mime_type': source['mime_type'], 'size_bytes': len(source['content']),
            'relative_path': path.name, 'sha256': source['sha256'],
            'source_index': position, 'purpose': source['purpose'], 'is_primary': int(position == 0), 'created_at': local_now_iso(),
        })
        return resource_id

    def link(self, db, member, medication_id, sources, created, *, reject_duplicates=False):
        self.catalog.detail(db, member, 'medication', medication_id)
        current = self.list(db, medication_id)
        existing_ids = {s['resource_id'] for s in current}
        existing_hashes = {s['sha256'] for s in current}
        seen = set()
        for source in sources:
            if source['resource_id'] in seen:
                raise ValueError('同一药品不能重复提交同一来源。')
            seen.add(source['resource_id'])
            if reject_duplicates and source['sha256'] in existing_hashes:
                raise ValueError('所选原件重复或已经关联到该药品。')
            existing_hashes.add(source['sha256'])
        position = len(current)
        for source in sources:
            resource_id = self.ensure(db, medication_id, source, position, created)
            if resource_id in existing_ids:
                continue
            position += 1
        if position != len(current):
            db.execute('UPDATE medication_data.medications SET updated_at=? WHERE medication_id=?', (local_now_iso(), medication_id))

    @staticmethod
    def list(db, medication_id):
        return [dict(row) for row in db.execute(
            'SELECT * FROM medication_data.medication_sources WHERE medication_id=? ORDER BY source_index', (medication_id,),
        )]

    def content(self, metadata):
        root = self.paths.medication_files_dir(self.account_id)
        path = root / metadata['relative_path']
        if path.is_symlink() or path.parent.resolve() != root.resolve() or not path.is_file():
            raise LookupError('药品原件不可用。')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != metadata['sha256']:
            raise ValueError('药品原件完整性校验失败。')
        return content

    def read(self, member, medication_id, resource_id):
        with self.catalog.transaction() as db:
            self.catalog.detail(db, member, 'medication', medication_id)
            row = next((s for s in self.list(db, medication_id) if s['resource_id'] == resource_id), None)
            if row is None:
                raise LookupError('药品原件已不存在或未关联到该药品。')
            return public_source(row), self.content(row)

    def drain_files(self):
        path = self.paths.medications_db(self.account_id)
        if not path.exists():
            return
        self.catalog.init_db()
        with connect(path) as db:
            jobs = cleanup_batch(db, 'medication_source_cleanup_outbox', scope=path)

            def clean(row):
                # A currently registered original is never removed by a stale cleanup job.
                if not db.execute('SELECT 1 FROM medication_sources WHERE relative_path=?', (row['relative_path'],)).fetchone():
                    root = self.paths.medication_files_dir(self.account_id)
                    target = root / row['relative_path']
                    if target.parent.resolve() != root.resolve() or target.is_symlink():
                        raise ValueError('原件路径无效。')
                    target.unlink(missing_ok=True)
                db.execute('DELETE FROM medication_source_cleanup_outbox WHERE cleanup_id=?', (row['cleanup_id'],))

            drain_cleanup_batch(jobs, clean)


def public_source(source):
    return {key: value for key, value in source.items() if key != 'relative_path'}
