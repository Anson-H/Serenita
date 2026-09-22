"""Persist current processing status on business changes, outside memory facts."""
from contextlib import contextmanager
import json
from pathlib import Path

from backend.app.domain.business_memory_status import FINAL_MEMORY_STATUSES, initial_memory_status
from backend.app.domain.memory.reception_scope import accepts_change
from backend.app.domain.memory.sources import BUSINESS_SOURCE_DATABASES
from backend.app.schemas.memory.values import SOURCE_CATEGORIES
from backend.app.storage.sqlite import connect, connect_read_only


def default_setting():
    return {'formation_state': 'enabled', 'source_categories': list(SOURCE_CATEGORIES), 'effective_at': None}


def read_setting(db, account, member):
    if db is None:
        return default_setting()
    row = db.execute('SELECT s.formation_state,s.source_categories_json,s.effective_at '
        'FROM settings_history s JOIN commits c USING(commit_id) WHERE s.account_id=? AND s.member_id=? '
        'ORDER BY c.sequence DESC LIMIT 1', (account, member)).fetchone()
    return {'formation_state': row[0], 'source_categories': json.loads(row[1]), 'effective_at': row[2]} if row else default_setting()


def status_at_creation(connection, change, fields, schema_alias):
    # Use the owning database, including attached member and medication stores.
    # Standalone ledgers have the same default policy as an account without settings.
    files = {row[1]: row[2] for row in connection.execute('PRAGMA database_list')}
    path = Path(files[schema_alias]) if files.get(schema_alias) else None
    setting = default_setting()
    if path and path.name in BUSINESS_SOURCE_DATABASES and path.parent.name == 'db_storage':
        account_root = path.parent.parent.parent
        if account_root.parent.name != 'accounts':
            raise ValueError('Business database is outside its owning account')
        memory_path = account_root / 'memory' / 'db_storage' / 'memory.db'
        if memory_path.is_file():
            with connect_read_only(memory_path) as db:
                setting = read_setting(db, account_root.name, change['member_id'])
    return initial_memory_status(change, fields, setting)


def processing_memory_status(db, account, member, database, change_id):
    """Read saved task results, never treating receipt or model output as success."""
    if db is None:
        return None
    attempt = db.execute("SELECT p.attempt_id,p.task_kind,p.processing_status FROM processing_attempts p JOIN commits c USING(commit_id) "
        "WHERE p.account_id=? AND p.member_id=? AND p.source_database=? AND p.change_id=? "
        "AND p.task_kind IN ('event_formation','intake_review') "
        "ORDER BY (p.task_kind='event_formation') DESC,c.sequence DESC LIMIT 1",
        (account, member, database, change_id)).fetchone()
    if attempt is None:
        return None
    value = attempt[2]
    if value in {'pending', 'running', 'failed'}:
        return {'pending': 'pending', 'running': 'processing', 'failed': 'failed'}[value]
    has_events = db.execute('SELECT 1 FROM event_evidence WHERE account_id=? AND member_id=? '
        'AND source_database=? AND change_id=? LIMIT 1', (account, member, database, change_id)).fetchone() is not None
    if value == 'cancelled':
        return 'failed' if attempt[1] == 'event_formation' else 'skipped'
    if value == 'completed' and attempt[1] == 'event_formation':
        return 'generated' if has_events else 'completed_empty'
    return 'pending'


class BusinessMemoryStatusRepository:
    def __init__(self, paths):
        self.paths = paths

    def path(self, account, database):
        from backend.app.storage.source_paths import registered_source_path
        return registered_source_path(self.paths, account, database)

    @contextmanager
    def memory(self, account):
        path = self.path(account, 'memory.db')
        if path.is_file():
            with connect_read_only(path) as db:
                yield db
        else:
            yield None

    def sync(self, account, member, keys):
        for database in sorted({database for database, _ in keys}):
            if database not in BUSINESS_SOURCE_DATABASES:
                continue
            path = self.path(account, database)
            if not path.is_file():
                continue
            with connect(path) as db:
                db.execute('BEGIN IMMEDIATE')
                with self.memory(account) as memory:
                    for source, change in keys:
                        if source != database:
                            continue
                        row = db.execute('SELECT memory_status FROM business_changes WHERE member_id=? AND change_id=?',
                            (member, change)).fetchone()
                        if row is None or row[0] in FINAL_MEMORY_STATUSES:
                            continue
                        status = processing_memory_status(memory, account, member, database, change)
                        if status is not None and status != row[0]:
                            db.execute('UPDATE business_changes SET memory_status=? WHERE member_id=? AND change_id=?',
                                (status, member, change))

    def fail_reception(self, account, member, database, change):
        path = self.path(account, database)
        if not path.is_file():
            return
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            with self.memory(account) as memory:
                if memory is not None and memory.execute("SELECT 1 FROM processing_attempts WHERE account_id=? "
                        "AND member_id=? AND source_database=? AND change_id=? AND task_kind='event_formation' LIMIT 1",
                        (account, member, database, change)).fetchone():
                    return
            db.execute("UPDATE business_changes SET memory_status='failed' WHERE member_id=? AND change_id=? "
                "AND memory_status IN ('pending','processing')", (member, change))

    def apply_settings(self, account, member):
        # Only unresolved business records are considered; settled results stay fixed.
        for database in BUSINESS_SOURCE_DATABASES:
            path = self.path(account, database)
            if not path.is_file():
                continue
            with connect(path) as db:
                db.execute('BEGIN IMMEDIATE')
                with self.memory(account) as memory:
                    setting = read_setting(memory, account, member)
                    for row in db.execute("SELECT * FROM business_changes WHERE member_id=? "
                            "AND memory_status IN ('pending','processing','failed')", (member,)).fetchall():
                        received = memory is not None and memory.execute("SELECT 1 FROM processing_attempts WHERE account_id=? "
                            "AND member_id=? AND source_database=? AND change_id=? AND task_kind='event_formation' LIMIT 1",
                            (account, member, database, row['change_id'])).fetchone()
                        if not received and not accepts_change(setting, dict(row)):
                            db.execute("UPDATE business_changes SET memory_status='skipped' WHERE change_id=?", (row['change_id'],))

    def recover(self, account, member, after=None, limit=100):
        # Task identifiers are the durable recovery source after a cross-database interruption.
        with self.memory(account) as memory:
            if memory is None:
                return None
            rows = memory.execute("SELECT DISTINCT source_database,change_id FROM processing_attempts "
                "WHERE account_id=? AND member_id=? AND task_kind IN ('event_formation','intake_review') "
                "AND source_database IS NOT NULL AND (source_database,change_id)>(?,?) "
                "ORDER BY source_database,change_id LIMIT ?", (account, member, *(after or ('','')), limit + 1)).fetchall()
        keys = [tuple(row) for row in rows[:limit]]
        self.sync(account, member, keys)
        return keys[-1] if len(rows) > limit else None
