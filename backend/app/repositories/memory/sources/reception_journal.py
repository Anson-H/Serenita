"""Latest input/output for each reception step before a memory task exists."""
from copy import deepcopy
from hashlib import sha256
import fcntl
import json
import os
from uuid import uuid4

from backend.app.core.time import local_now_iso
from backend.app.storage.paths import ensure_private_directory


class MemoryReceptionJournal:
    def __init__(self, paths, access, database, change_id):
        self.account_id, self.member_id = access.account_id, access.member_id
        self.actor_account_id = access.actor_account_id
        self.database, self.change_id = database, change_id
        key = sha256((database + '/' + change_id).encode()).hexdigest()
        self.path = paths.account_root(access.account_id) / 'memory' / 'reception' / access.member_id / (key + '.jsonl')
        self.receipt_id = str(uuid4())

    def append(self, step_id, parent, status, details, **errors):
        ensure_private_directory(self.path.parent)
        row = {'receipt_id': self.receipt_id, 'progress_id': str(uuid4()),
            'account_id': self.account_id, 'member_id': self.member_id, 'actor_account_id': self.actor_account_id,
            'source_database': self.database, 'change_id': self.change_id,
            'step_id': step_id, 'parent_step_id': parent, 'status': status,
            'details': deepcopy(details), 'submitted_at': local_now_iso(), **errors}
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+', encoding='utf-8') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            rows = [json.loads(line) for line in handle if line.strip()]
            rows = [old for old in rows if (old['step_id'], old['parent_step_id']) != (step_id, parent)]
            rows.append(row)
            handle.seek(0)
            handle.write(''.join(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n' for value in rows))
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())

    def read(self):
        if not self.path.exists():
            return []
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, encoding='utf-8') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            rows = [json.loads(line) for line in handle if line.strip()]
        return [row for row in rows if (row['account_id'], row['member_id'], row['source_database'], row['change_id']) ==
            (self.account_id, self.member_id, self.database, self.change_id)]
